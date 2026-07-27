"""Platform detection utilities."""

import platform
import sys


def get_platform() -> str:
    """Return normalized platform name: 'macos', 'windows', or 'linux'."""
    system = sys.platform
    if system == "darwin":
        return "macos"
    elif system == "win32":
        return "windows"
    else:
        return "linux"


def is_macos() -> bool:
    """Check if running on macOS."""
    return get_platform() == "macos"


def is_windows() -> bool:
    """Check if running on Windows."""
    return get_platform() == "windows"


def get_platform_info() -> dict:
    """Return detailed platform information."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
