"""macOS-native hotkey listener using Quartz CGEventTap.

This module provides ``QuartzHotkeyListener``, a ``HotkeyListener``
implementation that uses the macOS Quartz ``CGEventTap`` API directly
instead of pynput.  This avoids the ``TISCopyCurrentKeyboardInputSource``
thread-safety issue that causes macOS to abort the process with SIGABRT
when pynput is used from a background thread.

Requires macOS with Accessibility permissions granted for the application.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import platform
import threading
from collections.abc import Callable
from dataclasses import dataclass

from loguru import logger

from voice_dictation.hotkey.base import HotkeyListener
from voice_dictation.hotkey.hotkey_parser import HotkeyParser

try:
    from Quartz import (
        CFMachPortCreateRunLoopSource,
        CFRunLoopAddSource,
        CFRunLoopGetCurrent,
        CFRunLoopRemoveSource,
        CFRunLoopRun,
        CFRunLoopStop,
        CGEventGetFlags,
        CGEventGetIntegerValueField,
        CGEventTapCreate,
        kCGEventFlagMaskAlternate,
        kCGEventFlagMaskCommand,
        kCGEventFlagMaskControl,
        kCGEventFlagMaskShift,
        kCGEventKeyDown,
        kCGEventKeyUp,
        kCGEventTapOptionListenOnly,
        kCGHeadInsertEventTap,
        kCGSessionEventTap,
    )

    _QUARTZ_AVAILABLE = True
except ImportError:
    _QUARTZ_AVAILABLE = False

_MODIFIER_FLAG_MAP: dict[str, int] = {
    "cmd": kCGEventFlagMaskCommand if _QUARTZ_AVAILABLE else 1 << 20,
    "shift": kCGEventFlagMaskShift if _QUARTZ_AVAILABLE else 1 << 17,
    "ctrl": kCGEventFlagMaskControl if _QUARTZ_AVAILABLE else 1 << 18,
    "alt": kCGEventFlagMaskAlternate if _QUARTZ_AVAILABLE else 1 << 19,
}

_VK_MAP: dict[str, int] = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04,
    "g": 0x05, "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09,
    "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F,
    "y": 0x10, "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14,
    "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18, "9": 0x19,
    "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E,
    "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23,
    "enter": 0x24, "l": 0x25, "j": 0x26, "'": 0x27, "k": 0x28,
    ";": 0x29, "\\": 0x2A, ",": 0x2B, "/": 0x2C, "n": 0x2D,
    "m": 0x2E, ".": 0x2F, "tab": 0x30, "space": 0x31,
    "`": 0x32, "backspace": 0x33, "esc": 0x35,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76,
    "f5": 0x60, "f6": 0x61, "f7": 0x62, "f8": 0x64,
    "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
    "f13": 0x69, "f14": 0x6B, "f15": 0x71, "f16": 0x6A,
    "f17": 0x40, "f18": 0x4F, "f19": 0x50, "f20": 0x5A,
    "home": 0x73, "end": 0x77, "page_up": 0x74, "page_down": 0x79,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
    "delete": 0x75, "insert": 0x72,
}

_KCGEventKeyDown = 10 if not _QUARTZ_AVAILABLE else kCGEventKeyDown
_KCGEventKeyUp = 11 if not _QUARTZ_AVAILABLE else kCGEventKeyUp


@dataclass(frozen=True)
class _QuartzRegistration:
    hotkey_str: str
    modifiers: frozenset[str]
    vk_code: int
    on_activate: Callable[[], None]
    on_deactivate: Callable[[], None] | None


_CGEventTapCallBack = ctypes.CFUNCTYPE(
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.c_void_p,
)

_KCGKeyboardEventKeycode = 9


class QuartzHotkeyListener(HotkeyListener):
    """Hotkey listener using macOS Quartz ``CGEventTap``.

    Avoids the ``TISCopyCurrentKeyboardInputSource`` thread-safety issue
    present in pynput by using the low-level Quartz event tap directly.

    Supports two modes:

    - **push_to_talk**: ``on_activate`` fires on key-down, ``on_deactivate``
      fires on key-up.
    - **toggle**: each key-down toggles between activated/deactivated.

    Raises:
        RuntimeError: if ``start()`` is called on a non-macOS platform or
            without Accessibility permissions.
    """

    def __init__(self, mode: str = "push_to_talk") -> None:
        self._mode = mode
        self._running = False
        self._lock = threading.Lock()
        self._registrations: dict[str, _QuartzRegistration] = {}
        self._toggle_states: dict[str, bool] = {}
        self._activated: dict[str, bool] = {}
        self._thread: threading.Thread | None = None
        self._run_loop_source: object | None = None
        self._run_loop: object | None = None
        self._event_tap: object | None = None
        self._callback_ref: _CGEventTapCallBack | None = None

    def register(
        self,
        hotkey: str,
        on_activate: Callable[[], None],
        on_deactivate: Callable[[], None] | None = None,
    ) -> None:
        modifiers_str, key_str = HotkeyParser.parse(hotkey)
        vk_code = _VK_MAP.get(key_str)
        if vk_code is None:
            from voice_dictation.core.exceptions import InvalidHotkeyError

            raise InvalidHotkeyError(
                f"Key {key_str!r} has no macOS virtual key code mapping"
            )

        reg = _QuartzRegistration(
            hotkey_str=hotkey,
            modifiers=frozenset(modifiers_str),
            vk_code=vk_code,
            on_activate=on_activate,
            on_deactivate=on_deactivate,
        )
        with self._lock:
            self._registrations[hotkey] = reg
            self._toggle_states[hotkey] = False
            self._activated[hotkey] = False

    def unregister(self, hotkey: str) -> None:
        with self._lock:
            self._registrations.pop(hotkey, None)
            self._toggle_states.pop(hotkey, None)
            self._activated.pop(hotkey, None)

    def start(self) -> None:
        if platform.system() != "Darwin":
            raise RuntimeError(
                "QuartzHotkeyListener is only available on macOS"
            )
        if not _QUARTZ_AVAILABLE:
            raise RuntimeError(
                "Quartz framework is not available; install pyobjc-framework-Quartz"
            )
        with self._lock:
            if self._running:
                logger.warning("QuartzHotkeyListener already running")
                return
            try:
                self._create_event_tap()
                self._running = True
                logger.debug("QuartzHotkeyListener started")
            except Exception as e:
                logger.error(f"Failed to start QuartzHotkeyListener: {e}")
                self._cleanup()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            for hk in list(self._toggle_states):
                self._toggle_states[hk] = False
            self._cleanup()
            logger.debug("QuartzHotkeyListener stopped")

    def is_running(self) -> bool:
        return self._running

    def _create_event_tap(self) -> None:
        event_mask = (1 << _KCGEventKeyDown) | (1 << _KCGEventKeyUp)

        self._callback_ref = _CGEventTapCallBack(self._on_event)

        self._event_tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            event_mask,
            self._callback_ref,
            None,
        )

        if self._event_tap is None:
            logger.warning(
                "CGEventTapCreate returned NULL — Accessibility permissions "
                "may not be granted. Grant Accessibility access in "
                "System Settings > Privacy & Security > Accessibility"
            )
            raise RuntimeError(
                "CGEventTapCreate failed: ensure Accessibility permissions are granted"
            )

        self._run_loop_source = CFMachPortCreateRunLoopSource(
            None, self._event_tap, 0
        )

        self._thread = threading.Thread(
            target=self._run_loop_thread,
            name="quartz-hotkey-listener",
            daemon=True,
        )
        self._thread.start()

    def _run_loop_thread(self) -> None:
        self._run_loop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(
            self._run_loop, self._run_loop_source, 0x01  # kCFRunLoopCommonModes
        )
        CFRunLoopRun()

    def _cleanup(self) -> None:
        if self._run_loop is not None:
            try:
                CFRunLoopStop(self._run_loop)
            except Exception as e:
                logger.error(f"Error stopping CFRunLoop: {e}")
            self._run_loop = None

        if self._run_loop_source is not None:
            try:
                if self._run_loop is not None:
                    CFRunLoopRemoveSource(
                        self._run_loop, self._run_loop_source, 0x01
                    )
            except Exception as e:
                logger.error(f"Error removing CFRunLoopSource: {e}")
            self._run_loop_source = None

        self._event_tap = None
        self._callback_ref = None

        if self._thread is not None:
            self._thread = None

    def _on_event(
        self,
        proxy: int,
        event_type: int,
        event: int,
        user_info: int | None,
    ) -> int | None:
        if event_type not in (_KCGEventKeyDown, _KCGEventKeyUp):
            return event

        try:
            vk_code = CGEventGetIntegerValueField(event, _KCGKeyboardEventKeycode)
            flags = CGEventGetFlags(event)
        except Exception:
            return event

        active_modifiers: set[str] = set()
        for mod_name, flag_mask in _MODIFIER_FLAG_MAP.items():
            if flags & flag_mask:
                active_modifiers.add(mod_name)

        is_key_down = event_type == _KCGEventKeyDown

        with self._lock:
            for hk, reg in list(self._registrations.items()):
                if reg.vk_code != vk_code:
                    continue
                if reg.modifiers != frozenset(active_modifiers):
                    continue

                if is_key_down:
                    self._handle_key_down(hk, reg)
                else:
                    self._handle_key_up(hk, reg)

        return event

    def _handle_key_down(
        self, hotkey: str, reg: _QuartzRegistration
    ) -> None:
        try:
            if self._mode == "push_to_talk":
                if not self._activated.get(hotkey, False):
                    self._activated[hotkey] = True
                    reg.on_activate()
            else:
                if not self._toggle_states.get(hotkey, False):
                    self._toggle_states[hotkey] = True
                    self._activated[hotkey] = True
                    reg.on_activate()
                else:
                    self._toggle_states[hotkey] = False
                    self._activated[hotkey] = False
                    if reg.on_deactivate:
                        reg.on_deactivate()
        except Exception as e:
            logger.error(f"Hotkey callback error on key-down: {e}")

    def _handle_key_up(
        self, hotkey: str, reg: _QuartzRegistration
    ) -> None:
        if self._mode != "push_to_talk":
            return
        try:
            if self._activated.get(hotkey, False):
                self._activated[hotkey] = False
                if reg.on_deactivate:
                    reg.on_deactivate()
        except Exception as e:
            logger.error(f"Hotkey callback error on key-up: {e}")
