"""pynput-based hotkey listener implementation."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from loguru import logger

from voice_dictation.hotkey.base import HotkeyListener
from voice_dictation.hotkey.hotkey_parser import KeyModifier, KeyCode, parse_hotkey

_PYNPUT_SPECIAL_MAP: dict[str, Any] = {}
_PYNPUT_MODIFIER_MAP: dict[KeyModifier, set[Any]] = {}
_PYNPUT_MAPS_INITIALIZED = False


def _init_pynput_maps() -> None:
    global _PYNPUT_MAPS_INITIALIZED
    if _PYNPUT_MAPS_INITIALIZED:
        return
    _PYNPUT_MAPS_INITIALIZED = True
    try:
        from pynput.keyboard import Key

        _PYNPUT_SPECIAL_MAP.update({
            "space": Key.space,
            "enter": Key.enter,
            "tab": Key.tab,
            "esc": Key.esc,
            "backspace": Key.backspace,
            "delete": Key.delete,
            "home": Key.home,
            "end": Key.end,
            "page_up": Key.page_up,
            "page_down": Key.page_down,
            "left": Key.left,
            "right": Key.right,
            "up": Key.up,
            "down": Key.down,
            "insert": Key.insert,
            "f1": Key.f1,
            "f2": Key.f2,
            "f3": Key.f3,
            "f4": Key.f4,
            "f5": Key.f5,
            "f6": Key.f6,
            "f7": Key.f7,
            "f8": Key.f8,
            "f9": Key.f9,
            "f10": Key.f10,
            "f11": Key.f11,
            "f12": Key.f12,
        })
        _PYNPUT_MODIFIER_MAP.update({
            KeyModifier.CTRL: {Key.ctrl, Key.ctrl_l, Key.ctrl_r},
            KeyModifier.CMD: {Key.cmd, Key.cmd_l, Key.cmd_r},
            KeyModifier.ALT: {Key.alt, Key.alt_l, Key.alt_r},
            KeyModifier.SHIFT: {Key.shift, Key.shift_l, Key.shift_r},
        })
    except Exception:
        pass


class _HotkeyRegistration:
    __slots__ = (
        "hotkey_str",
        "combo",
        "pynput_key",
        "pynput_modifiers",
        "on_activate",
        "on_deactivate",
    )

    def __init__(
        self,
        hotkey_str: str,
        combo: Any,
        pynput_key: Any,
        pynput_modifiers: list[set[Any]],
        on_activate: Callable[[], None],
        on_deactivate: Callable[[], None] | None,
    ) -> None:
        self.hotkey_str = hotkey_str
        self.combo = combo
        self.pynput_key = pynput_key
        self.pynput_modifiers = pynput_modifiers
        self.on_activate = on_activate
        self.on_deactivate = on_deactivate


class PynputListener(HotkeyListener):
    """Hotkey listener using pynput.keyboard.Listener.

    Supports two modes:
      - push_to_talk: on_activate when full combo pressed, on_deactivate when released
      - toggle: on_activate on first press, on_deactivate on second press
    """

    def __init__(self, mode: str = "push_to_talk") -> None:
        self._mode = mode
        self._listener: Any | None = None
        self._running = False
        self._lock = threading.Lock()
        self._toggle_state = False
        self._pressed_keys: set[Any] = set()
        self._combo_active = False
        self._registrations: list[_HotkeyRegistration] = []

    def register(
        self,
        hotkey: str,
        on_activate: Callable[[], None],
        on_deactivate: Callable[[], None] | None = None,
    ) -> None:
        combo = parse_hotkey(hotkey)
        _init_pynput_maps()

        pynput_key = self._to_pynput_key(combo.key)
        pynput_modifiers = self._to_pynput_modifiers(combo.modifiers)

        reg = _HotkeyRegistration(
            hotkey_str=hotkey,
            combo=combo,
            pynput_key=pynput_key,
            pynput_modifiers=pynput_modifiers,
            on_activate=on_activate,
            on_deactivate=on_deactivate,
        )
        with self._lock:
            self._registrations.append(reg)

    def start(self) -> None:
        with self._lock:
            if self._running:
                logger.warning("Hotkey listener already running")
                return
            try:
                from pynput.keyboard import Listener

                self._listener = Listener(
                    on_press=self._on_press,
                    on_release=self._on_release,
                )
                self._listener.start()
                self._running = True
                logger.debug("Hotkey listener started")
            except Exception as e:
                logger.error(f"Failed to start hotkey listener: {e}")
                self._listener = None

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._pressed_keys.clear()
            self._combo_active = False
            self._toggle_state = False
            if self._listener is not None:
                try:
                    self._listener.stop()
                except Exception as e:
                    logger.error(f"Error stopping hotkey listener: {e}")
                self._listener = None
            logger.debug("Hotkey listener stopped")

    def is_running(self) -> bool:
        return self._running

    def _on_press(self, key: Any) -> None:
        with self._lock:
            self._pressed_keys.add(self._normalize_key(key))
            for reg in list(self._registrations):
                self._check_press(reg)

    def _on_release(self, key: Any) -> None:
        with self._lock:
            self._pressed_keys.discard(self._normalize_key(key))
            for reg in list(self._registrations):
                self._check_release(reg)

    def _check_press(self, reg: _HotkeyRegistration) -> None:
        try:
            if self._mode == "push_to_talk":
                if self._is_combo_pressed(reg) and not self._combo_active:
                    self._combo_active = True
                    reg.on_activate()
            else:
                if self._is_combo_pressed(reg):
                    if not self._toggle_state:
                        self._toggle_state = True
                        reg.on_activate()
                    else:
                        self._toggle_state = False
                        if reg.on_deactivate:
                            reg.on_deactivate()
        except Exception as e:
            logger.error(f"Hotkey callback error: {e}")

    def _check_release(self, reg: _HotkeyRegistration) -> None:
        try:
            if self._mode == "push_to_talk":
                if self._combo_active and not self._is_combo_pressed(reg):
                    self._combo_active = False
                    if reg.on_deactivate:
                        reg.on_deactivate()
        except Exception as e:
            logger.error(f"Hotkey callback error: {e}")

    def _is_combo_pressed(self, reg: _HotkeyRegistration) -> bool:
        for pressed in self._pressed_keys:
            if self._keys_match(pressed, reg.pynput_key):
                break
        else:
            return False
        for mod_set in reg.pynput_modifiers:
            found = any(
                any(self._keys_match(pressed, mod) for mod in mod_set)
                for pressed in self._pressed_keys
            )
            if not found:
                return False
        return True

    def _keys_match(self, pressed: Any, target: Any) -> bool:
        if pressed == target:
            return True
        if isinstance(pressed, str) and isinstance(target, str):
            return pressed.lower() == target.lower()
        if isinstance(pressed, str) and hasattr(target, "char") and target.char is not None:
            return pressed.lower() == target.char.lower()
        if isinstance(target, str) and hasattr(pressed, "char") and pressed.char is not None:
            return pressed.char.lower() == target.lower()
        return False

    def _to_pynput_key(self, key: KeyCode) -> Any:
        if key.char is not None:
            try:
                from pynput.keyboard import KeyCode as PynputKeyCode

                return PynputKeyCode.from_char(key.char)
            except Exception:
                return key.char
        if key.special is not None and key.special in _PYNPUT_SPECIAL_MAP:
            return _PYNPUT_SPECIAL_MAP[key.special]
        return key.char or key.special

    def _to_pynput_modifiers(self, modifiers: frozenset[KeyModifier]) -> list[set[Any]]:
        result: list[set[Any]] = []
        for mod in modifiers:
            if mod in _PYNPUT_MODIFIER_MAP:
                result.append(_PYNPUT_MODIFIER_MAP[mod])
        return result

    @staticmethod
    def _normalize_key(key: Any) -> Any:
        if hasattr(key, "char") and key.char is not None:
            return key.char.lower() if isinstance(key.char, str) else key
        if hasattr(key, "vk") and key.vk is not None:
            return key.vk
        return key
