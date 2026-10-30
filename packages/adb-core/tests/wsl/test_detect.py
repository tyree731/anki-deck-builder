"""Tests for adb_core/wsl/detect.py."""

import pytest

from adb_core.wsl import detect


@pytest.mark.platform("linux", "macos", "windows", "wsl")
def test_detection_matches_this_machine(ci_platform: str):
    """test_detection_matches_this_machine: on a real machine, is_wsl() and interop_enabled() are true exactly under
    WSL, where drive C is visible under the mount root; native Linux, macOS and Windows get false for both."""
    on_wsl = ci_platform == "wsl"
    assert detect.is_wsl() is on_wsl
    assert detect.interop_enabled() is on_wsl
    if on_wsl:
        assert (detect.mount_root() / "c" / "Windows").is_dir()
