"""pynput-based hotkey listener implementations.

Two listener classes are provided:

- ``PynputHotkeyListener`` (preferred): uses ``pynput.keyboard.GlobalHotKeys``
  for press detection plus a separate ``pynput.keyboard.Listener`` for release
  tracking (push-to-talk). Supports ``unregister()`` and thread-safe
  operation.

- ``PynputListener`` (legacy): uses a single ``pynput.keyboard.Listener``
  for both press and release. Kept for backwards compatibility with existing
  integration tests.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from loguru import logger

from voice_dictation.hotkey.base import HotkeyListener
from voice_dictation.hotkey.hotkey_parser import (
    HotkeyParser,
    KeyCode,
    KeyModifier,
    parse_hotkey,
)

# ---------------------------------------------------------------------------
# pynput key mapping tables (populated lazily)
# ---------------------------------------------------------------------------

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

        # Build special-key map defensively: not every pynput platform
        # provides every key (e.g. macOS lacks ``Key.insert``).  Use
        # ``getattr`` so missing attributes are silently skipped instead of
        # aborting the whole initialization.
        _special_names = [
            "space",
            "enter",
            "tab",
            "esc",
            "backspace",
            "delete",
            "home",
            "end",
            "page_up",
            "page_down",
            "left",
            "right",
            "up",
            "down",
            "insert",
        ]
        _special_names.extend(f"f{i}" for i in range(1, 21))

        for name in _special_names:
            key_val = getattr(Key, name, None)
            if key_val is not None:
                _PYNPUT_SPECIAL_MAP[name] = key_val

        # Build modifier map the same way: left/right variants may be absent
        # on some platforms, so collect whatever exists.
        _modifier_variants: dict[KeyModifier, list[str]] = {
            KeyModifier.CTRL: ["ctrl", "ctrl_l", "ctrl_r"],
            KeyModifier.CMD: ["cmd", "cmd_l", "cmd_r"],
            KeyModifier.ALT: ["alt", "alt_l", "alt_r"],
            KeyModifier.SHIFT: ["shift", "shift_l", "shift_r"],
        }

        for mod, variants in _modifier_variants.items():
            mod_set: set[Any] = set()
            for v in variants:
                key_val = getattr(Key, v, None)
                if key_val is not None:
                    mod_set.add(key_val)
            if mod_set:
                _PYNPUT_MODIFIER_MAP[mod] = mod_set
    except Exception as e:
        logger.debug(f"pynput key maps initialization issue: {e}")


# ---------------------------------------------------------------------------
# Internal registration record
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# PynputHotkeyListener (preferred, uses GlobalHotKeys + release Listener)
# ---------------------------------------------------------------------------


class PynputHotkeyListener(HotkeyListener):
    """Hotkey listener using ``pynput.keyboard.GlobalHotKeys`` for press
    detection and a separate ``pynput.keyboard.Listener`` for release tracking.

    Supports two modes:
      - **push_to_talk**: ``on_activate`` fires on combo press; ``on_deactivate``
        fires when all keys in the combo are released.
      - **toggle**: ``on_activate`` fires on the first press, ``on_deactivate``
        on the second press, and so on.
    """

    def __init__(self, mode: str = "push_to_talk") -> None:
        self._mode = mode
        self._global_hotkeys: Any | None = None
        self._release_listener: Any | None = None
        self._running = False
        self._lock = threading.Lock()
        self._registrations: dict[str, _HotkeyRegistration] = {}
        self._toggle_states: dict[str, bool] = {}
        self._activated: dict[str, bool] = {}
        self._pressed_keys: set[Any] = set()

    def set_mode(self, mode: str) -> None:
        """Switch activation mode at runtime (push_to_talk <-> toggle).

        Unlike CarbonHotkeyListener, PynputHotkeyListener does not need
        to re-install any system hooks — we only need to update the
        internal _mode flag and reset toggle states.
        """
        valid_modes = ("push_to_talk", "toggle")
        if mode not in valid_modes:
            logger.warning(f"Unknown mode: {mode!r} not in {valid_modes}")
            return
        old = self._mode
        self._mode = mode
        with self._lock:
            for hk in list(self._toggle_states):
                self._toggle_states[hk] = False
                self._activated[hk] = False
        logger.info(f"PynputHotkeyListener mode: {old} -> {mode}")

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
            self._registrations[hotkey] = reg
            self._toggle_states[hotkey] = False
            self._activated[hotkey] = False

    def unregister(self, hotkey: str) -> None:
        with self._lock:
            self._registrations.pop(hotkey, None)
            self._toggle_states.pop(hotkey, None)
            self._activated.pop(hotkey, None)

    def start(self) -> None:
        with self._lock:
            if self._running:
                logger.warning("Hotkey listener already running")
                return
            try:
                self._start_listeners()
                self._running = True
                logger.debug("PynputHotkeyListener started")
            except Exception as e:
                logger.error(f"Failed to start hotkey listener: {e}")
                self._cleanup_listeners()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._pressed_keys.clear()
            for hk in list(self._toggle_states):
                self._toggle_states[hk] = False
            self._cleanup_listeners()
            logger.debug("PynputHotkeyListener stopped")

    def is_running(self) -> bool:
        return self._running

    def _start_listeners(self) -> None:
        from pynput.keyboard import GlobalHotKeys, Listener

        hotkey_map: dict[str, Callable[[], None]] = {}
        for hk in self._registrations:
            pynput_fmt = HotkeyParser.to_pynput_format(hk)
            hotkey_map[pynput_fmt] = self._make_press_callback(hk)

        if hotkey_map:
            self._global_hotkeys = GlobalHotKeys(hotkey_map)
            self._global_hotkeys.start()

        self._release_listener = Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._release_listener.start()

    def _cleanup_listeners(self) -> None:
        for listener_attr in ("_global_hotkeys", "_release_listener"):
            listener = getattr(self, listener_attr, None)
            if listener is not None:
                try:
                    listener.stop()
                except Exception as e:
                    logger.error(f"Error stopping {listener_attr}: {e}")
                setattr(self, listener_attr, None)

    def _make_press_callback(self, hotkey: str) -> Callable[[], None]:
        def callback() -> None:
            with self._lock:
                reg = self._registrations.get(hotkey)
                if reg is None:
                    return
                try:
                    if self._mode == "push_to_talk":
                        if self._activated.get(hotkey, False):
                            return
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
                    logger.error(f"Hotkey callback error: {e}")

        return callback

    def _on_press(self, key: Any) -> None:
        with self._lock:
            self._pressed_keys.add(self._normalize_key(key))

    def _on_release(self, key: Any) -> None:
        with self._lock:
            self._pressed_keys.discard(self._normalize_key(key))
            if self._mode == "push_to_talk":
                for hk, reg in list(self._registrations.items()):
                    if (
                        reg.on_deactivate
                        and self._activated.get(hk, False)
                        and not self._is_combo_pressed(reg)
                    ):
                        self._activated[hk] = False
                        reg.on_deactivate()

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

    @staticmethod
    def _keys_match(pressed: Any, target: Any) -> bool:
        if pressed == target:
            return True
        if isinstance(pressed, str) and isinstance(target, str):
            return pressed.lower() == target.lower()
        if isinstance(pressed, str) and hasattr(target, "char") and target.char is not None:
            return pressed.lower() == target.char.lower()
        if isinstance(target, str) and hasattr(pressed, "char") and pressed.char is not None:
            return pressed.char.lower() == target.lower()
        return False

    @staticmethod
    def _to_pynput_key(key: KeyCode) -> Any:
        if key.char is not None:
            try:
                from pynput.keyboard import KeyCode as PynputKeyCode

                return PynputKeyCode.from_char(key.char)
            except Exception:
                return key.char
        if key.special is not None and key.special in _PYNPUT_SPECIAL_MAP:
            return _PYNPUT_SPECIAL_MAP[key.special]
        return key.char or key.special

    @staticmethod
    def _to_pynput_modifiers(modifiers: frozenset[KeyModifier]) -> list[set[Any]]:
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


# ---------------------------------------------------------------------------
# PynputListener (legacy, single Listener for both press and release)
# ---------------------------------------------------------------------------


class PynputListener(HotkeyListener):
    """Hotkey listener using a single ``pynput.keyboard.Listener``.

    .. deprecated::
        Prefer :class:`PynputHotkeyListener` which uses ``GlobalHotKeys`` for
        more reliable combo detection. This class is retained for backwards
        compatibility with existing integration tests.

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
        self._combo_active: dict[str, bool] = {}
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
            self._combo_active[hotkey] = False

    def unregister(self, hotkey: str) -> None:
        with self._lock:
            self._registrations = [r for r in self._registrations if r.hotkey_str != hotkey]
            self._combo_active.pop(hotkey, None)

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
            for hk in list(self._combo_active):
                self._combo_active[hk] = False
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
                if self._is_combo_pressed(reg) and not self._combo_active.get(
                    reg.hotkey_str, False
                ):
                    self._combo_active[reg.hotkey_str] = True
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
            if (
                self._mode == "push_to_talk"
                and self._combo_active.get(reg.hotkey_str, False)
                and not self._is_combo_pressed(reg)
            ):
                self._combo_active[reg.hotkey_str] = False
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

    @staticmethod
    def _keys_match(pressed: Any, target: Any) -> bool:
        if pressed == target:
            return True
        if isinstance(pressed, str) and isinstance(target, str):
            return pressed.lower() == target.lower()
        if isinstance(pressed, str) and hasattr(target, "char") and target.char is not None:
            return pressed.lower() == target.char.lower()
        if isinstance(target, str) and hasattr(pressed, "char") and pressed.char is not None:
            return pressed.char.lower() == target.lower()
        return False

    @staticmethod
    def _to_pynput_key(key: KeyCode) -> Any:
        if key.char is not None:
            try:
                from pynput.keyboard import KeyCode as PynputKeyCode

                return PynputKeyCode.from_char(key.char)
            except Exception:
                return key.char
        if key.special is not None and key.special in _PYNPUT_SPECIAL_MAP:
            return _PYNPUT_SPECIAL_MAP[key.special]
        return key.char or key.special

    @staticmethod
    def _to_pynput_modifiers(modifiers: frozenset[KeyModifier]) -> list[set[Any]]:
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
