"""Platform abstraction layer."""

from voice_dictation.platform.detect import (
    get_platform,
    get_platform_info,
    is_macos,
    is_windows,
)

__all__ = ["get_platform", "is_macos", "is_windows", "get_platform_info"]
