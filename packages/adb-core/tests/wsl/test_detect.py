"""Tests for adb_core/wsl/detect.py."""

from pathlib import Path

import pytest

from adb_core.wsl import detect

WSL2 = "5.15.153.1-microsoft-standard-WSL2"


def _kernel(monkeypatch, release: str, system: str = "Linux") -> None:
    monkeypatch.setattr(detect.platform, "system", lambda: system)
    monkeypatch.setattr(detect.platform, "release", lambda: release)


def test_is_wsl_reads_the_kernel_release(tmp_path: Path, monkeypatch):
    """test_is_wsl_reads_the_kernel_release: WSL 2 and WSL 1 kernels say "microsoft" (in either case); other Linux
    kernels and other systems are not WSL."""
    for release in (WSL2, "4.4.0-19041-Microsoft"):
        _kernel(monkeypatch, release)
        assert detect.is_wsl(tmp_path)
    _kernel(monkeypatch, "6.8.0-45-generic")
    assert not detect.is_wsl(tmp_path)
    _kernel(monkeypatch, WSL2, system="Darwin")
    assert not detect.is_wsl(tmp_path)


def test_is_wsl_recognizes_a_custom_kernel(tmp_path: Path, monkeypatch):
    """test_is_wsl_recognizes_a_custom_kernel: a kernel without "microsoft" still counts when /run/WSL exists."""
    _kernel(monkeypatch, "6.6.36-custom")
    (tmp_path / "run/WSL").mkdir(parents=True)
    assert detect.is_wsl(tmp_path)


def test_is_wsl_excludes_containers(tmp_path: Path, monkeypatch):
    """test_is_wsl_excludes_containers: Docker and Podman containers running on WSL's kernel are not WSL."""
    _kernel(monkeypatch, WSL2)
    (tmp_path / ".dockerenv").write_text("")
    assert not detect.is_wsl(tmp_path)
    (tmp_path / ".dockerenv").unlink()
    (tmp_path / "run").mkdir()
    (tmp_path / "run/.containerenv").write_text("")
    assert not detect.is_wsl(tmp_path)


def test_interop_enabled_reads_the_binfmt_registration(tmp_path: Path):
    """test_interop_enabled_reads_the_binfmt_registration: WSLInterop, or WSLInterop-late on some systemd setups,
    must read "enabled"; a missing or disabled registration means Windows programs can't start."""
    binfmt = tmp_path / "proc/sys/fs/binfmt_misc"
    binfmt.mkdir(parents=True)
    assert not detect.interop_enabled(tmp_path)
    (binfmt / "WSLInterop-late").write_text("enabled\ninterpreter /init\nflags: PF\noffset 0\nmagic 4d5a\n")
    assert detect.interop_enabled(tmp_path)
    (binfmt / "WSLInterop").write_text("disabled\ninterpreter /init\n")
    assert not detect.interop_enabled(tmp_path)


def test_mount_root_reads_wsl_conf(tmp_path: Path):
    """test_mount_root_reads_wsl_conf: [automount] root moves the Windows drives, quoted or not; without it they're
    under /mnt."""
    conf = tmp_path / "wsl.conf"
    assert detect.mount_root(conf) == Path("/mnt")
    conf.write_text('# drives\n[boot]\nsystemd=true\n\n[automount]\nroot = "/drives/"\n')
    assert detect.mount_root(conf) == Path("/drives")
    conf.write_text("[automount]\nroot = /\n")
    assert detect.mount_root(conf) == Path("/")


@pytest.mark.platform("linux", "windows", "wsl")
def test_detection_matches_this_machine(ci_platform: str):
    """test_detection_matches_this_machine: on a real machine, is_wsl() is true exactly under WSL, where Windows
    programs can be started and drive C is visible under the mount root."""
    on_wsl = ci_platform == "wsl"
    assert detect.is_wsl() is on_wsl
    if on_wsl:
        assert detect.interop_enabled()
        assert (detect.mount_root() / "c" / "Windows").is_dir()
