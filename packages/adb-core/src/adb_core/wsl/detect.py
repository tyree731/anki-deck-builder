"""Recognize WSL, and how it reaches Windows: interop and the drive mounts."""

import configparser
import platform
from pathlib import Path

# A custom WSL kernel may not say "microsoft"; WSL's interop registration and /run/WSL still do.
_WSL_MARKERS = ("proc/sys/fs/binfmt_misc/WSLInterop", "proc/sys/fs/binfmt_misc/WSLInterop-late", "run/WSL")
_CONTAINER_MARKERS = (".dockerenv", "run/.containerenv")  # Docker, Podman


def is_wsl(root: Path = Path("/")) -> bool:
    """Whether this is Linux under Windows Subsystem for Linux, outside a container.

    Args:
        root: The filesystem root to probe.

    Returns:
        True under WSL 1 or WSL 2. False elsewhere, including Docker and Podman containers
        that run on WSL's kernel.
    """
    if platform.system() != "Linux":
        return False
    wsl = "microsoft" in platform.release().lower() or any((root / m).exists() for m in _WSL_MARKERS)
    return wsl and not any((root / m).exists() for m in _CONTAINER_MARKERS)


def interop_enabled(root: Path = Path("/")) -> bool:
    """Whether WSL can start Windows programs.

    WSL registers Windows executables with binfmt_misc as WSLInterop (WSLInterop-late on
    some systemd setups); the registration reads "enabled" unless interop is turned off.

    Args:
        root: The filesystem root to probe.

    Returns:
        True when Windows programs can be started from WSL.
    """
    for name in ("WSLInterop", "WSLInterop-late"):
        try:
            return "enabled" in (root / "proc/sys/fs/binfmt_misc" / name).read_text()
        except OSError:
            continue
    return False


def mount_root(config: Path = Path("/etc/wsl.conf")) -> Path:
    """Where WSL mounts the Windows drives: `/mnt`, unless wsl.conf's `[automount] root` says otherwise.

    Args:
        config: The WSL configuration file.

    Returns:
        The mount root; drive C is its `c` folder.
    """
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read(config, encoding="utf-8")
        root = parser.get("automount", "root", fallback="/mnt")
    except configparser.Error, OSError, UnicodeDecodeError:
        root = "/mnt"
    return Path(root.strip().strip("\"'") or "/mnt")
