"""Tests for adb_core/wsl/windows.py."""

from pathlib import Path

import pytest

from adb_core.wsl import windows
from adb_testkit import wait_for_file


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
