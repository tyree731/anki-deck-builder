"""Real-platform tests: those marked `platform`, run with `pytest --platform linux|macos|windows|wsl`.

They use the real OS, and the stand-in for Anki changes this user's file associations
while a test runs, so they're meant for CI runners (see .github/workflows/platforms.yml).
"""

import json
import os
import plistlib
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from adb_core import wsl

PLATFORMS = ("linux", "macos", "windows", "wsl")

_LSREGISTER = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

# the macOS stand-in: an AppleScript app whose open handler records the file's path.
_APPLET = r"""on open theFiles
	set target to POSIX path of (item 1 of theFiles)
	do shell script "printf '%s\n' " & quoted form of target & " > " & quoted form of "{marker}"
end open
"""

# declares a type for the .apkg extension and claims it, replacing the applet's catch-all claim.
_APKG_TYPE = "org.ankideckbuilder.standin.apkg"
_INFO = {
    "CFBundleIdentifier": "org.ankideckbuilder.standin",
    "CFBundleDocumentTypes": [
        {
            "CFBundleTypeName": "Anki deck package",
            "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Owner",
            "LSItemContentTypes": [_APKG_TYPE],
        }
    ],
    "UTImportedTypeDeclarations": [
        {
            "UTTypeIdentifier": _APKG_TYPE,
            "UTTypeDescription": "Anki deck package",
            "UTTypeConformsTo": ["public.data"],
            "UTTypeTagSpecification": {"public.filename-extension": ["apkg"]},
        }
    ],
}

# which app Launch Services would open a file with (JavaScript for Automation).
_OPENS_WITH = (
    "ObjC.import('AppKit');"
    "const app = $.NSWorkspace.sharedWorkspace.URLForApplicationToOpenURL($.NSURL.fileURLWithPath({path}));"
    "app.isNil() ? '' : app.path.js"
)

_MIME = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-apkg"><glob pattern="*.apkg"/></mime-type>
</mime-info>
"""

# makes the stand-in this user's app for .apkg files; prints the association it replaced.
_REGISTER = """$ErrorActionPreference = 'Stop'
$classes = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Software\\Classes')
$extension = $classes.CreateSubKey('.apkg')
$previous = $extension.GetValue('')
$extension.SetValue('', 'adbstandin.apkg')
$classes.CreateSubKey('adbstandin.apkg\\shell\\open\\command').SetValue('', $env:ADB_STAND_IN_COMMAND)
if ($null -ne $previous) { Write-Output $previous }
"""

# removes the stand-in and puts back the association it replaced, if any.
_UNREGISTER = """$ErrorActionPreference = 'Stop'
$classes = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Software\\Classes')
$classes.DeleteSubKeyTree('adbstandin.apkg', $false)
$extension = $classes.CreateSubKey('.apkg')
if ($env:ADB_STAND_IN_PREVIOUS) { $extension.SetValue('', $env:ADB_STAND_IN_PREVIOUS) }
else { $extension.DeleteValue('', $false) }
"""


def wait_for_file(path: Path, timeout: float = 30.0) -> str:
    """Wait for a file another process writes, such as the stand-in's record of what it opened.

    Args:
        path: The file to wait for.
        timeout: How many seconds to wait.

    Returns:
        Its text, once it exists and isn't empty.

    Raises:
        AssertionError: Nothing was written in time.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file() and (text := path.read_text(errors="replace").strip()):
            return text
        time.sleep(0.25)
    raise AssertionError(f"nothing was written to {path} within {timeout:.0f}s")


@contextmanager
def stand_in_anki(platform: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Make a stand-in for Anki this user's app for .apkg files, until the block ends.

    The stand-in writes the path it was asked to open to the marker file it yields.
    ANKI_DECK_BUILDER_ANKI points `find_anki()` at a placeholder; under WSL it's an .exe,
    so Anki counts as installed on Windows.

    Args:
        platform: linux, macos, windows or wsl.
        tmp_path: A temporary folder for the stand-in's files.
        monkeypatch: Sets the environment for the test's duration.

    Yields:
        The marker file the stand-in writes.
    """
    marker = tmp_path / "opened.txt"
    if platform == "macos":
        app = _register_with_launch_services(marker, tmp_path)
        monkeypatch.setenv("ANKI_DECK_BUILDER_ANKI", str(app))
        try:
            yield marker
        finally:
            subprocess.run([_LSREGISTER, "-u", str(app)], check=False)
            shutil.rmtree(app.parent, ignore_errors=True)
        return
    if platform == "linux":
        _register_with_xdg(marker, tmp_path, monkeypatch)
        monkeypatch.setenv("ANKI_DECK_BUILDER_ANKI", str(_placeholder(tmp_path / "anki")))
        yield marker
        return
    target = wsl.windows_path(marker) if platform == "wsl" else str(marker)
    previous = _powershell(platform, _REGISTER, ADB_STAND_IN_COMMAND=f'cmd.exe /d /c >"{target}" echo("%1"')
    monkeypatch.setenv("ANKI_DECK_BUILDER_ANKI", str(_placeholder(tmp_path / "Anki.exe")))
    try:
        yield marker
    finally:
        _powershell(platform, _UNREGISTER, ADB_STAND_IN_PREVIOUS=previous)


def _placeholder(path: Path) -> Path:
    path.write_text("")
    return path


def _build_applet(marker: Path, folder: Path) -> Path:
    # an app that claims .apkg files and records what it's asked to open. editing Info.plist
    # breaks the applet's signature, so it's signed again (ad hoc).
    app = folder / "Anki Stand-in.app"
    script = folder / "stand-in.applescript"
    literal = str(marker).replace("\\", "\\\\").replace('"', '\\"')
    script.write_text(_APPLET.replace("{marker}", literal))
    subprocess.run(["osacompile", "-o", str(app), str(script)], check=True)
    info = app / "Contents" / "Info.plist"
    info.write_bytes(plistlib.dumps(plistlib.loads(info.read_bytes()) | _INFO))
    subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True, capture_output=True)
    return app


def _opens_with(path: Path) -> str:
    script = _OPENS_WITH.replace("{path}", json.dumps(str(path)))
    done = subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True)
    return done.stdout.strip()


def _register_with_launch_services(marker: Path, tmp_path: Path, timeout: float = 30.0) -> Path:
    # registers the stand-in, then waits until Launch Services would open an .apkg with it.
    # Launch Services won't let an app in a temporary folder open files (it flags it
    # in-temp-dir and launch-disabled), so the app is built under ~/Library/Caches instead.
    home = Path.home() / "Library" / "Caches" / "anki-deck-builder-tests"
    home.mkdir(parents=True, exist_ok=True)
    app = _build_applet(marker, Path(tempfile.mkdtemp(prefix="stand-in-", dir=home)))
    subprocess.run([_LSREGISTER, "-f", str(app)], check=True)
    probe = tmp_path / "probe.apkg"
    probe.write_bytes(b"")
    deadline = time.monotonic() + timeout
    while True:
        opens_with = _opens_with(probe)
        if opens_with and Path(opens_with).resolve() == app.resolve():
            return app
        if time.monotonic() > deadline:
            raise AssertionError(f"Launch Services opens .apkg files with {opens_with or 'nothing'}, not the stand-in")
        time.sleep(0.5)


def _register_with_xdg(marker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # desktop file and MIME type in temporary XDG folders, so the user's own stay untouched.
    # xdg-open only reads desktop files when there's a display (CI uses xvfb-run).
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.fail("xdg-open needs a display to use desktop files: run the tests under xvfb-run")
    data, config = tmp_path / "xdg-data", tmp_path / "xdg-config"
    (data / "applications").mkdir(parents=True)
    (data / "mime" / "packages").mkdir(parents=True)
    config.mkdir()
    handler = tmp_path / "stand-in"
    handler.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$1\" > {shlex.quote(str(marker))}\n")
    handler.chmod(0o755)
    (data / "applications" / "adb-stand-in.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Stand-in for Anki\n"
        f'Exec="{handler}" %f\nMimeType=application/x-apkg;\nNoDisplay=true\n'
    )
    (data / "mime" / "packages" / "adb-stand-in.xml").write_text(_MIME)
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    subprocess.run(["update-mime-database", str(data / "mime")], check=True)
    subprocess.run(["xdg-mime", "default", "adb-stand-in.desktop", "application/x-apkg"], check=True)


def _powershell(platform: str, script: str, **values: str) -> str:
    # runs Windows PowerShell natively or from WSL; values arrive as environment variables
    # (forwarded into Windows by WSLENV), so nothing is quoted into the script.
    powershell = wsl.powershell() if platform == "wsl" else "powershell.exe"
    if powershell is None:
        raise RuntimeError("Windows PowerShell isn't reachable from WSL")
    env = dict(os.environ, **values)
    env["WSLENV"] = ":".join(filter(None, [os.environ.get("WSLENV"), *values]))
    done = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        env=env,
        cwd=Path(powershell).parent if platform == "wsl" else None,
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise RuntimeError(f"PowerShell failed: {(done.stderr or done.stdout).strip()}")
    return done.stdout.strip()
