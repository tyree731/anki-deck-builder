"""Preflight: verify the local environment before a run.

Running this through uv also resolves and caches every package the pipeline uses, so
the first real phase does not stall on downloads. It checks the packages import, a
headless-capable browser exists (the Refine phase needs it to look at every card), and
the input directory is usable. It makes no network calls of its own.
"""

import importlib
import os
import shutil
import sys
from pathlib import Path

import click

from adb_core.common import EXIT_FAIL, find_anki, find_browser

PACKAGES = [
    ("genanki", "genanki"),
    ("anki", "anki (import validator + renderer)"),
    ("PIL", "Pillow"),
    ("pypdfium2", "pypdfium2 (PDF pages)"),
    ("jsonschema", "jsonschema"),
]


def check(name: str, passed: bool, detail: str = "", optional: bool = False) -> bool:
    """Print one check result.

    Args:
        name: What was checked.
        passed: Whether it passed.
        detail: Extra text shown after the name.
        optional: A failure only warns.

    Returns:
        True when this is a failed required check.
    """
    label = "ok" if passed else ("WARN" if optional else "FAIL")
    click.echo(f"  [{label}] {name}" + (f": {detail}" if detail else ""))
    return not passed and not optional


def run_checks(input_dir: Path) -> int:
    """Check Python, packages, a browser and the input folder, printing one line each.

    Args:
        input_dir: The folder the run will read and write inside.

    Returns:
        The number of failed required checks.
    """
    failed = 0
    failed += check(f"Python {sys.version.split()[0]} (via uv)", sys.version_info[:2] >= (3, 14), "requires 3.14+")
    for module, label in PACKAGES:
        try:
            importlib.import_module(module)
            failed += check(label, True)
        except Exception as exc:
            failed += check(label, False, f"{type(exc).__name__}: {exc}")
    try:
        importlib.import_module("pillow_heif")
        check("pillow-heif (HEIC photos)", True)
    except Exception:
        check("pillow-heif (HEIC photos)", False, "HEIC files will be skipped", optional=True)
    browser = find_browser()
    failed += check(
        "headless browser for card screenshots",
        browser is not None,
        browser or "install Google Chrome or Chromium, or set ANKI_DECK_BUILDER_CHROME",
    )
    anki = find_anki()
    check(
        "Anki desktop, to open the finished deck in it (optional)", anki is not None, anki or "not found", optional=True
    )
    is_dir = input_dir.is_dir()
    failed += check(f"input dir {input_dir}", is_dir, "" if is_dir else "not a directory")
    if is_dir:
        free_gb = shutil.disk_usage(input_dir).free / 1e9
        failed += check(f"free disk {free_gb:.1f} GB", free_gb >= 1.0, "need 1 GB for page renders and screenshots")
        failed += check("input dir writable (run and output dirs go inside it)", os.access(input_dir, os.W_OK))
    return failed


@click.command(name="preflight")
@click.argument("input_dir", type=click.Path(path_type=Path))
def cli(input_dir: Path) -> None:
    """Check the environment, the browser and INPUT_DIR before a run (exit 1 on any failure)."""
    failed = run_checks(input_dir.expanduser())
    click.echo("preflight: " + ("PASS" if not failed else f"FAIL ({failed} required check(s))"))
    if failed:
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    cli()
