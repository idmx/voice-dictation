"""Hotkey management module."""

from voice_dictation.hotkey.base import HotkeyListener
from voice_dictation.hotkey.hotkey_parser import (
    HotkeyCombo,
    HotkeyParser,
    KeyCode,
    KeyModifier,
    parse_hotkey,
)
from voice_dictation.hotkey.pynput_listener import PynputHotkeyListener, PynputListener

__all__ = [
    "HotkeyListener",
    "HotkeyParser",
    "PynputHotkeyListener",
    "PynputListener",
    "parse_hotkey",
    "HotkeyCombo",
    "KeyCode",
    "KeyModifier",
]
