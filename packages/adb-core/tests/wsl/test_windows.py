"""Tests for adb_core/wsl/windows.py."""

import subprocess
from pathlib import Path

import pytest

from adb_core.wsl import windows
from adb_testkit import wait_for_file

WIN_PATH = "\\\\wsl.localhost\\Ubuntu\\home\\kid\\Deck's [v2] $x.apkg"
POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"


class FakeWindows:
    """Stands in for subprocess.run: wslpath answers WIN_PATH, PowerShell answers `result`."""

    def __init__(self):
        self.runs: list[tuple[list[str], dict]] = []
        self.result = subprocess.CompletedProcess([], 0, stdout="", stderr="")

    def run(self, argv: list[str], **kwargs) -> subprocess.CompletedProcess:
        self.runs.append((argv, kwargs))
        if argv[0] == "wslpath":
            return subprocess.CompletedProcess(argv, 0, stdout=WIN_PATH + "\n", stderr="")
        return self.result


@pytest.fixture
def fake(monkeypatch) -> FakeWindows:
    """WSL with interop on and Windows PowerShell on the Windows PATH."""
    fake = FakeWindows()
    monkeypatch.setattr(windows.subprocess, "run", fake.run)
    monkeypatch.setattr(windows, "interop_enabled", lambda: True)
    monkeypatch.setattr(windows.shutil, "which", lambda name: POWERSHELL if name == "powershell.exe" else None)
    return fake


def test_windows_path_asks_wslpath(fake: FakeWindows, tmp_path: Path):
    """test_windows_path_asks_wslpath: the absolute path goes to `wslpath -aw`, and its answer comes back trimmed."""
    assert windows.windows_path(tmp_path / "deck.apkg") == WIN_PATH
    assert fake.runs[0][0] == ["wslpath", "-aw", str((tmp_path / "deck.apkg").resolve())]


def test_powershell_falls_back_to_the_mount_root(tmp_path: Path, monkeypatch):
    """test_powershell_falls_back_to_the_mount_root: without Windows PATH entries, PowerShell is found on drive C
    under the configured mount root."""
    monkeypatch.setattr(windows.shutil, "which", lambda name: None)
    monkeypatch.setattr(windows, "mount_root", lambda: tmp_path)
    assert windows.powershell() is None
    exe = tmp_path / "c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert windows.powershell() == str(exe)


def test_open_on_windows_keeps_the_path_out_of_the_script(fake: FakeWindows, tmp_path: Path, monkeypatch):
    """test_open_on_windows_keeps_the_path_out_of_the_script: a name with a quote, brackets and $ reaches PowerShell
    in an environment variable forwarded by WSLENV, never inside the script, which opens it literally from
    PowerShell's own folder."""
    monkeypatch.setenv("WSLENV", "USERPROFILE/p")
    windows.open_on_windows(tmp_path / "deck.apkg")
    argv, kwargs = fake.runs[-1]
    assert argv[:3] == [POWERSHELL, "-NoProfile", "-NonInteractive"]
    assert "Deck's" not in argv[-1] and "Invoke-Item -LiteralPath $env:ADB_OPEN_PATH" in argv[-1]
    assert (kwargs["env"]["ADB_OPEN_PATH"], kwargs["env"]["WSLENV"]) == (WIN_PATH, "USERPROFILE/p:ADB_OPEN_PATH")
    assert kwargs["cwd"] == Path(POWERSHELL).parent


def test_open_on_windows_reports_failures(fake: FakeWindows, tmp_path: Path, monkeypatch):
    """test_open_on_windows_reports_failures: Windows' own message comes back as a WslError, and with interop off
    PowerShell is never run."""
    fake.result = subprocess.CompletedProcess([], 1, stdout="", stderr="not found: C:\\x.apkg")
    with pytest.raises(windows.WslError, match="not found"):
        windows.open_on_windows(tmp_path / "deck.apkg")
    monkeypatch.setattr(windows, "interop_enabled", lambda: False)
    before = len(fake.runs)
    with pytest.raises(windows.WslError, match=r"\[interop\] enabled"):
        windows.open_on_windows(tmp_path / "deck.apkg")
    assert len(fake.runs) == before


@pytest.mark.platform("wsl")
def test_windows_path_and_powershell_on_real_wsl(tmp_path: Path):
    """test_windows_path_and_powershell_on_real_wsl: on real WSL, a drive path becomes C:\\..., a Linux path becomes
    a \\\\wsl path into the distribution, and Windows PowerShell is found."""
    assert windows.windows_path(Path("/mnt/c/Windows")).upper().startswith("C:\\WINDOWS")
    assert windows.windows_path(tmp_path).lower().startswith("\\\\wsl")
    assert windows.powershell() is not None


@pytest.mark.platform("wsl")
def test_open_on_windows_on_real_wsl(tmp_path: Path, stand_in_anki: Path):
    """test_open_on_windows_on_real_wsl: on real WSL, Windows opens a file from the Linux filesystem, named with a
    quote, brackets and $, with the app registered for it."""
    deck = tmp_path / "Deck's [v2] $x.apkg"
    deck.write_bytes(b"deck")
    windows.open_on_windows(deck)
    assert deck.name in wait_for_file(stand_in_anki)
