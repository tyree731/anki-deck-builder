"""Hand files from WSL to Windows: Windows paths, Windows PowerShell, and opening with the default app."""

import os
import shutil
import subprocess
from pathlib import Path

from adb_core.wsl.detect import interop_enabled, mount_root


class WslError(Exception):
    """Windows can't be reached from WSL, or refused the request."""


# opens a path literally (Start-Process would expand wildcards in it); any error stops the script.
_OPEN = (
    "$ErrorActionPreference = 'Stop'; "
    'if (-not (Test-Path -LiteralPath $env:ADB_OPEN_PATH)) { throw "not found: $env:ADB_OPEN_PATH" }; '
    "Invoke-Item -LiteralPath $env:ADB_OPEN_PATH"
)


def windows_path(path: Path) -> str:
    """The Windows form of a path, from `wslpath -aw`.

    Args:
        path: A file on a Windows drive (`/mnt/c/...`) or in the Linux filesystem.

    Returns:
        A drive path (`C:\\Users\\...`) or a UNC path into the distribution (`\\\\wsl.localhost\\...`).

    Raises:
        WslError: wslpath failed or isn't available.
    """
    try:
        done = subprocess.run(["wslpath", "-aw", str(path.resolve())], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise WslError(f"couldn't convert {path} to a Windows path with wslpath: {exc}") from exc
    return done.stdout.strip()


def powershell() -> str | None:
    """Locate Windows PowerShell from WSL.

    Returns:
        Its path, via WSL's Windows PATH entries or under the drive mount root, or None.
    """
    found = shutil.which("powershell.exe")
    if found:
        return found
    fallback = mount_root() / "c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    return str(fallback) if fallback.exists() else None


def open_on_windows(path: Path) -> None:
    """Open a file with the Windows app registered for its type.

    The Windows path reaches PowerShell in an environment variable forwarded by WSLENV, so
    no file name can break the script. PowerShell runs from its own folder, so a Linux
    working directory never becomes a UNC path on the Windows side.

    Args:
        path: The file to open.

    Raises:
        WslError: Interop is off, PowerShell isn't reachable, or Windows couldn't open the file.
    """
    if not interop_enabled():
        raise WslError("WSL can't start Windows programs: check that [interop] enabled isn't false in /etc/wsl.conf")
    ps = powershell()
    if ps is None:
        raise WslError("Windows PowerShell isn't reachable from WSL")
    env = dict(os.environ, ADB_OPEN_PATH=windows_path(path))
    env["WSLENV"] = ":".join(filter(None, [os.environ.get("WSLENV"), "ADB_OPEN_PATH"]))
    try:
        done = subprocess.run(
            [ps, "-NoProfile", "-NonInteractive", "-Command", _OPEN],
            env=env,
            cwd=Path(ps).parent,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WslError(f"couldn't run Windows PowerShell to open {path}: {exc}") from exc
    if done.returncode != 0:
        raise WslError(f"Windows couldn't open {path}: {(done.stderr or done.stdout).strip()}")
