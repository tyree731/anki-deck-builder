"""WSL (Windows Subsystem for Linux) detection and interop, using only the standard library."""

from adb_core.wsl.detect import interop_enabled, is_wsl, mount_root
from adb_core.wsl.windows import WslError, open_on_windows, powershell, windows_path

__all__ = ["WslError", "interop_enabled", "is_wsl", "mount_root", "open_on_windows", "powershell", "windows_path"]
