"""Run `adb` commands in tests: in-process with click's CliRunner, or through uv as SKILL.md does."""

import subprocess

import click
from click.testing import CliRunner, Result

from adb_core.common import SKILL_ROOT


def run_adb(command: str, *args, check: bool = True) -> subprocess.CompletedProcess:
    """Run `adb <command>` exactly as SKILL.md does, from a neutral working directory.

    Args:
        command: The adb subcommand, e.g. "state".
        *args: Its arguments (converted with str()).
        check: Raise when the command exits non-zero.

    Returns:
        The completed process, with text stdout and stderr.

    Raises:
        AssertionError: check is true and the command failed; the message includes its output.
    """
    proc = subprocess.run(
        ["uv", "run", "--quiet", "--frozen", "--project", str(SKILL_ROOT), "adb", command, *[str(a) for a in args]],
        capture_output=True,
        text=True,
        timeout=900,
        cwd="/",
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            f"adb {command} {args} exited {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def invoke(command: click.Command, *args) -> Result:
    """Invoke a click command in-process, for tests of what a command writes.

    Args:
        command: The command or group, e.g. `imgtool.cli`.
        *args: Command-line arguments (converted with str()).

    Returns:
        The click result.

    Raises:
        AssertionError: The command failed; the message includes its output.
    """
    result = CliRunner().invoke(command, [str(a) for a in args])
    if result.exit_code != 0:
        detail = f"\n{result.exception!r}" if result.exception and not isinstance(result.exception, SystemExit) else ""
        raise AssertionError(f"exit {result.exit_code}\nOUTPUT:\n{result.output}{detail}")
    return result
