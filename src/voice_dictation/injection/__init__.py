"""Text injection module."""

from voice_dictation.injection.base import TextInjector


def create_injector(
    method: str = "clipboard",
    restore_clipboard: bool = True,
    **kwargs: object,
) -> TextInjector:
    """Create platform-appropriate text injector."""
    from voice_dictation.platform.detect import is_macos, is_windows

    if is_macos():
        from voice_dictation.injection.macos_injector import MacOSTextInjector

        return MacOSTextInjector(
            method=method,
            restore_clipboard=restore_clipboard,
            **kwargs,
        )
    elif is_windows():
        from voice_dictation.injection.windows_injector import WindowsTextInjector

        return WindowsTextInjector(
            method=method,
            restore_clipboard=restore_clipboard,
            **kwargs,
        )
    else:
        raise NotImplementedError(
            "Text injection not supported on this platform"
        )


__all__ = ["TextInjector", "create_injector"]
