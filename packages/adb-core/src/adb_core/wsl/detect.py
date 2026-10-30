"""Recognize WSL, and how it reaches Windows: interop and the drive mounts."""

import configparser
import platform
from pathlib import Path

_BINFMT = Path("/proc/sys/fs/binfmt_misc")
_WSL_CONF = Path("/etc/wsl.conf")
# a custom WSL kernel may not say "microsoft"; WSL's interop registration and /run/WSL still do.
_WSL_MARKERS = (_BINFMT / "WSLInterop", _BINFMT / "WSLInterop-late", Path("/run/WSL"))
_CONTAINER_MARKERS = (Path("/.dockerenv"), Path("/run/.containerenv"))  # Docker, Podman


def is_wsl() -> bool:
    """Whether this is Linux under Windows Subsystem for Linux, outside a container.

    Returns:
        True under WSL 1 or WSL 2. False elsewhere, including Docker and Podman containers
        that run on WSL's kernel.
    """
    if platform.system() != "Linux":
        return False
    wsl = "microsoft" in platform.release().lower() or any(m.exists() for m in _WSL_MARKERS)
    return wsl and not any(m.exists() for m in _CONTAINER_MARKERS)


def interop_enabled() -> bool:
    """Whether WSL can start Windows programs.

    WSL registers Windows executables with binfmt_misc as WSLInterop (WSLInterop-late on
    some systemd setups); the registration reads "enabled" unless interop is turned off.

    Returns:
        True when Windows programs can be started from WSL.
    """
    for name in ("WSLInterop", "WSLInterop-late"):
        try:
            return "enabled" in (_BINFMT / name).read_text()
        except OSError:
            continue
    return False


def mount_root() -> Path:
    """Where WSL mounts the Windows drives: `/mnt`, unless wsl.conf's `[automount] root` says otherwise.

    Returns:
        The mount root; drive C is its `c` folder.
    """
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read(_WSL_CONF, encoding="utf-8")
        root = parser.get("automount", "root", fallback="/mnt")
    except configparser.Error, OSError, UnicodeDecodeError:
        root = "/mnt"
    return Path(root.strip().strip("\"'") or "/mnt")
