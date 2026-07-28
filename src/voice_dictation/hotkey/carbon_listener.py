"""macOS-native hotkey listener using Carbon RegisterEventHotKey.

This module provides ``CarbonHotkeyListener``, a ``HotkeyListener``
implementation that uses the Carbon Event Manager's ``RegisterEventHotKey``
API.  This is the standard macOS mechanism for registering system-wide
hotkeys and has two critical advantages over alternatives:

1. **No Accessibility permissions required** — unlike ``CGEventTap``,
   ``RegisterEventHotKey`` works without granting Accessibility access.
2. **No TIS/TSM calls** — unlike ``pynput``, it never touches the
   Text Input Source APIs that cause ``SIGABRT`` when called from a
   background thread.

Events are dispatched through the main thread's run loop (which pystray
already runs), so callbacks fire on the main thread.
"""

from __future__ import annotations

import ctypes
import platform
import threading
from collections.abc import Callable
from dataclasses import dataclass

from loguru import logger

from voice_dictation.hotkey.base import HotkeyListener
from voice_dictation.hotkey.hotkey_parser import HotkeyParser

# ---------------------------------------------------------------------------
# Load HIToolbox framework via ctypes
# ---------------------------------------------------------------------------

_HITOOLBOX_PATH = (
    "/System/Library/Frameworks/Carbon.framework/"
    "Frameworks/HIToolbox.framework/HIToolbox"
)

try:
    _lib = ctypes.cdll.LoadLibrary(_HITOOLBOX_PATH)
    _CARBON_AVAILABLE = True
except OSError:
    _CARBON_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Event class 'keyb'
K_EVENT_CLASS_KEYBOARD = 0x6B657962

# Event kinds
K_EVENT_HOT_KEY_PRESSED = 5
K_EVENT_HOT_KEY_RELEASED = 6

# Event parameter name 'hkid'
TYPE_EVENT_HOT_KEY_ID = 0x686B6964

# kEventParamDirectObject = '----' — the direct object parameter
K_EVENT_PARAM_DIRECT_OBJECT = 0x2D2D2D2D

# Modifier key constants for RegisterEventHotKey
CMD_KEY = 0x0100
SHIFT_KEY = 0x0200
OPTION_KEY = 0x0800
CONTROL_KEY = 0x1000

_MODIFIER_CARBON_MAP: dict[str, int] = {
    "cmd": CMD_KEY,
    "shift": SHIFT_KEY,
    "alt": OPTION_KEY,
    "ctrl": CONTROL_KEY,
}

# Our hotkey signature — 'VDHK' (Voice Dictation HotKey)
_HOTKEY_SIGNATURE = 0x56444848  # 'VDHH'

# macOS virtual key codes (same as QuartzHotkeyListener)
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


# ---------------------------------------------------------------------------
# ctypes structures
# ---------------------------------------------------------------------------


class EventHotKeyID(ctypes.Structure):
    """Carbon EventHotKeyID structure."""

    _fields_ = [
        ("signature", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
    ]


class EventTypeSpec(ctypes.Structure):
    """Carbon EventTypeSpec structure."""

    _fields_ = [
        ("eventClass", ctypes.c_uint32),
        ("eventKind", ctypes.c_uint32),
    ]


# Event handler callback type: OSStatus(EventHandlerCallRef, EventRef, void*)
EventHandlerProcPtr = ctypes.CFUNCTYPE(
    ctypes.c_int,  # OSStatus
    ctypes.c_void_p,  # EventHandlerCallRef
    ctypes.c_void_p,  # EventRef
    ctypes.c_void_p,  # userData
)


# ---------------------------------------------------------------------------
# Configure function signatures (only if Carbon is available)
# ---------------------------------------------------------------------------

if _CARBON_AVAILABLE:
    _lib.GetApplicationEventTarget.argtypes = []
    _lib.GetApplicationEventTarget.restype = ctypes.c_void_p

    _lib.InstallEventHandler.argtypes = [
        ctypes.c_void_p,  # inTarget
        EventHandlerProcPtr,  # inHandler
        ctypes.c_uint32,  # inNumTypes
        ctypes.POINTER(EventTypeSpec),  # inList
        ctypes.c_void_p,  # inUserData
        ctypes.POINTER(ctypes.c_void_p),  # outRef
    ]
    _lib.InstallEventHandler.restype = ctypes.c_int

    _lib.RegisterEventHotKey.argtypes = [
        ctypes.c_uint32,  # hotKeyCode
        ctypes.c_uint32,  # hotKeyModifiers
        EventHotKeyID,  # inHotKeyID (passed by value)
        ctypes.c_void_p,  # inHotKeyTarget
        ctypes.c_uint32,  # inOptions
        ctypes.POINTER(ctypes.c_void_p),  # outRef
    ]
    _lib.RegisterEventHotKey.restype = ctypes.c_int

    _lib.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
    _lib.UnregisterEventHotKey.restype = ctypes.c_int

    _lib.RemoveEventHandler.argtypes = [ctypes.c_void_p]
    _lib.RemoveEventHandler.restype = ctypes.c_int

    _lib.GetEventKind.argtypes = [ctypes.c_void_p]
    _lib.GetEventKind.restype = ctypes.c_uint32

    _lib.GetEventParameter.argtypes = [
        ctypes.c_void_p,  # inEvent
        ctypes.c_uint32,  # inName
        ctypes.c_uint32,  # inDesiredType
        ctypes.POINTER(ctypes.c_uint32),  # outActualType
        ctypes.c_uint32,  # inBufferSize
        ctypes.POINTER(ctypes.c_uint32),  # outActualSize
        ctypes.c_void_p,  # outData
    ]
    _lib.GetEventParameter.restype = ctypes.c_int


# ---------------------------------------------------------------------------
# Registration record
# ---------------------------------------------------------------------------


@dataclass
class _CarbonRegistration:
    """Internal registration record for a single hotkey."""

    hotkey_id: int
    hotkey_str: str
    vk_code: int
    carbon_modifiers: int
    on_activate: Callable[[], None]
    on_deactivate: Callable[[], None] | None
    ref: int = 0  # EventHotKeyRef (opaque pointer)


# ---------------------------------------------------------------------------
# CarbonHotkeyListener
# ---------------------------------------------------------------------------


class CarbonHotkeyListener(HotkeyListener):
    """Hotkey listener using macOS Carbon ``RegisterEventHotKey``.

    This is the recommended approach for macOS global hotkeys:

    - **No Accessibility permissions required** (unlike CGEventTap).
    - **No TIS/TSM calls** (unlike pynput — no SIGABRT crash).
    - Events dispatched through the main thread's run loop.

    Supports two modes:

    - **push_to_talk**: ``on_activate`` fires on key-down, ``on_deactivate``
      fires on key-up.
    - **toggle**: each key-down toggles between activated/deactivated.

    Raises:
        RuntimeError: if ``start()`` is called on a non-macOS platform or
            without the HIToolbox framework.
    """

    def __init__(self, mode: str = "push_to_talk") -> None:
        self._mode = mode
        self._running = False
        self._lock = threading.Lock()
        self._registrations: dict[str, _CarbonRegistration] = {}
        self._id_to_hotkey: dict[int, str] = {}
        self._next_id: int = 1
        self._toggle_states: dict[str, bool] = {}
        self._activated: dict[str, bool] = {}
        self._event_handler_ref: int = 0
        self._callback_ref: EventHandlerProcPtr | None = None
        self._target: int = 0

    def set_mode(self, mode: str) -> None:
        """Switch activation mode at runtime.

        No need to re-install the Carbon event handler — it always
        listens for both PRESSED and RELEASED. Only the internal
        _mode flag and toggle state need updating.
        """
        valid_modes = ("push_to_talk", "toggle")
        if mode not in valid_modes:
            logger.warning(f"Unknown mode: {mode!r} not in {valid_modes}")
            return
        old = self._mode
        self._mode = mode
        # Reset toggle states when switching modes
        for hk in list(self._toggle_states):
            self._toggle_states[hk] = False
            self._activated[hk] = False
        logger.info(f"CarbonHotkeyListener mode: {old} -> {mode}")

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

        carbon_modifiers = 0
        for mod in modifiers_str:
            carbon_modifiers |= _MODIFIER_CARBON_MAP.get(mod, 0)

        with self._lock:
            hotkey_id = self._next_id
            self._next_id += 1

            reg = _CarbonRegistration(
                hotkey_id=hotkey_id,
                hotkey_str=hotkey,
                vk_code=vk_code,
                carbon_modifiers=carbon_modifiers,
                on_activate=on_activate,
                on_deactivate=on_deactivate,
            )
            self._registrations[hotkey] = reg
            self._id_to_hotkey[hotkey_id] = hotkey
            self._toggle_states[hotkey] = False
            self._activated[hotkey] = False

    def unregister(self, hotkey: str) -> None:
        with self._lock:
            reg = self._registrations.pop(hotkey, None)
            if reg is not None:
                self._id_to_hotkey.pop(reg.hotkey_id, None)
                self._toggle_states.pop(hotkey, None)
                self._activated.pop(hotkey, None)

                # If listener is running, unregister from Carbon
                if reg.ref != 0 and _CARBON_AVAILABLE:
                    try:
                        _lib.UnregisterEventHotKey(reg.ref)
                    except Exception as e:
                        logger.error(f"Error unregistering hotkey: {e}")

    def start(self) -> None:
        if platform.system() != "Darwin":
            raise RuntimeError("CarbonHotkeyListener is only available on macOS")
        if not _CARBON_AVAILABLE:
            raise RuntimeError(
                "HIToolbox framework is not available (macOS only)"
            )

        with self._lock:
            if self._running:
                logger.warning("CarbonHotkeyListener already running")
                return

            self._running = True

            # Carbon event handlers and hotkey registration must run on
            # the main thread (the one with a CFRunLoop).  Use
            # dispatch_async to schedule the work there.
            self._dispatch_to_main(self._do_start)

            logger.info("CarbonHotkeyListener start dispatched to main thread")

    def _do_start(self) -> None:
        """Actual start — runs on the main thread."""
        try:
            self._install_event_handler()
            self._register_all_hotkeys()
            logger.info("CarbonHotkeyListener started on main thread")
        except Exception as e:
            logger.error(f"Failed to start CarbonHotkeyListener: {e}")
            with self._lock:
                self._running = False
            self._cleanup()

    @staticmethod
    def _dispatch_to_main(block: Callable[[], None]) -> None:
        """Dispatch *block* to the main thread's run loop.

        Uses ``dispatch_async`` on the main queue.  Falls back to a
        thread if libdispatch is unavailable (should not happen on macOS).
        """
        import threading

        try:
            libdispatch = ctypes.cdll.LoadLibrary(
                "/usr/lib/system/libdispatch.dylib"
            )

            dispatch_get_main_queue = libdispatch.dispatch_get_main_queue
            dispatch_get_main_queue.restype = ctypes.c_void_p
            dispatch_get_main_queue.argtypes = []

            dispatch_async_f = libdispatch.dispatch_async_f
            dispatch_async_f.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.CFUNCTYPE(None, ctypes.c_void_p),
            ]
            dispatch_async_f.restype = None

            callback = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(lambda _: block())
            # Keep reference alive to prevent GC
            CarbonHotkeyListener._pending_callbacks.append(callback)
            # Prevent unbounded growth — keep only recent callbacks
            if len(CarbonHotkeyListener._pending_callbacks) > 10:
                CarbonHotkeyListener._pending_callbacks = CarbonHotkeyListener._pending_callbacks[-5:]

            dispatch_async_f(dispatch_get_main_queue(), None, callback)
        except Exception as e:
            logger.debug(f"dispatch_async unavailable ({e}), using thread fallback")
            threading.Thread(target=block, daemon=True).start()

    _pending_callbacks: list = []

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            for hk in list(self._toggle_states):
                self._toggle_states[hk] = False
                self._activated[hk] = False
            self._cleanup()
            logger.debug("CarbonHotkeyListener stopped")

    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Internal: Carbon setup
    # ------------------------------------------------------------------

    def _install_event_handler(self) -> None:
        """Install the Carbon event handler for hotkey events.

        Always subscribes to BOTH PRESSED and RELEASED events regardless
        of mode. This allows switching mode at runtime without needing to
        re-install the event handler (which causes -9866 errors).
        """
        self._target = _lib.GetApplicationEventTarget()
        if not self._target:
            raise RuntimeError("GetApplicationEventTarget returned NULL")

        # Always listen for both event types
        num_types = 2
        event_types = (EventTypeSpec * 2)(
            EventTypeSpec(K_EVENT_CLASS_KEYBOARD, K_EVENT_HOT_KEY_PRESSED),
            EventTypeSpec(K_EVENT_CLASS_KEYBOARD, K_EVENT_HOT_KEY_RELEASED),
        )

        # Create callback — must keep reference alive
        self._callback_ref = EventHandlerProcPtr(self._on_carbon_event)

        handler_ref = ctypes.c_void_p(0)
        status = _lib.InstallEventHandler(
            self._target,
            self._callback_ref,
            num_types,
            event_types,
            None,
            ctypes.byref(handler_ref),
        )

        if status != 0:
            raise RuntimeError(f"InstallEventHandler failed with status {status}")

        self._event_handler_ref = handler_ref.value or 0
        logger.debug(f"Event handler installed (ref={self._event_handler_ref})")

    def _register_all_hotkeys(self) -> None:
        """Register all pending hotkeys with Carbon."""
        for reg in self._registrations.values():
            hotkey_id = EventHotKeyID(
                signature=_HOTKEY_SIGNATURE,
                id=reg.hotkey_id,
            )

            ref = ctypes.c_void_p(0)
            status = _lib.RegisterEventHotKey(
                reg.vk_code,
                reg.carbon_modifiers,
                hotkey_id,
                self._target,
                0,  # options: 0 = non-exclusive
                ctypes.byref(ref),
            )

            if status != 0:
                logger.error(
                    f"RegisterEventHotKey failed for '{reg.hotkey_str}' "
                    f"with status {status}"
                )
                continue

            reg.ref = ref.value or 0
            logger.debug(
                f"Registered hotkey '{reg.hotkey_str}' "
                f"(id={reg.hotkey_id}, ref={reg.ref})"
            )

    def _cleanup(self) -> None:
        """Unregister all hotkeys and remove the event handler."""
        for reg in self._registrations.values():
            if reg.ref != 0:
                try:
                    _lib.UnregisterEventHotKey(reg.ref)
                except Exception as e:
                    logger.error(f"Error unregistering hotkey: {e}")
                reg.ref = 0

        # Remove the Carbon event handler to stop receiving events
        if self._event_handler_ref != 0 and _CARBON_AVAILABLE:
            try:
                _lib.RemoveEventHandler(self._event_handler_ref)
                logger.debug("Carbon event handler removed")
            except Exception as e:
                logger.debug(f"Error removing event handler: {e}")

        self._event_handler_ref = 0
        self._callback_ref = None
        CarbonHotkeyListener._pending_callbacks.clear()
        self._target = 0

    # ------------------------------------------------------------------
    # Carbon event callback (called on main thread's run loop)
    # ------------------------------------------------------------------

    def _on_carbon_event(
        self,
        handler_call_ref: int,
        event_ref: int,
        user_data: int | None,
    ) -> int:
        """Carbon event handler callback.

        Called by the Carbon Event Manager on the main thread's run loop
        when a registered hotkey is pressed or released.
        """
        try:
            event_kind = _lib.GetEventKind(event_ref)
            logger.info(f"Carbon event received: kind={event_kind}")

            # Extract EventHotKeyID from the event
            hotkey_id_struct = EventHotKeyID()
            actual_size = ctypes.c_uint32(0)
            status = _lib.GetEventParameter(
                event_ref,
                K_EVENT_PARAM_DIRECT_OBJECT,  # inName
                TYPE_EVENT_HOT_KEY_ID,  # inDesiredType
                None,  # outActualType
                ctypes.sizeof(hotkey_id_struct),  # inBufferSize
                ctypes.byref(actual_size),  # outActualSize
                ctypes.byref(hotkey_id_struct),  # outData
            )

            if status != 0:
                logger.error(f"GetEventParameter failed with status {status}")
                return 0

            hotkey_id = hotkey_id_struct.id
            logger.info(
                f"Hotkey event: id={hotkey_id}, "
                f"signature={hotkey_id_struct.signature:#x}"
            )

            with self._lock:
                hotkey_str = self._id_to_hotkey.get(hotkey_id)
                if hotkey_str is None:
                    return 0

                reg = self._registrations.get(hotkey_str)
                if reg is None:
                    return 0

                if event_kind == K_EVENT_HOT_KEY_PRESSED:
                    self._handle_key_down(hotkey_str, reg)
                elif event_kind == K_EVENT_HOT_KEY_RELEASED:
                    self._handle_key_up(hotkey_str, reg)

        except Exception as e:
            logger.error(f"Error in Carbon event handler: {e}")

        return 0  # noErr

    # ------------------------------------------------------------------
    # Hotkey event dispatching
    # ------------------------------------------------------------------

    def _handle_key_down(
        self, hotkey: str, reg: _CarbonRegistration
    ) -> None:
        try:
            if self._mode == "push_to_talk":
                if not self._activated.get(hotkey, False):
                    self._activated[hotkey] = True
                    reg.on_activate()
            else:  # toggle
                # In toggle mode, ALWAYS call on_activate.
                # The pipeline decides whether to start or stop recording
                # based on the current state (see _on_hotkey_down in pipeline.py).
                reg.on_activate()
        except Exception as e:
            logger.error(f"Hotkey callback error on key-down: {e}")

    def _handle_key_up(
        self, hotkey: str, reg: _CarbonRegistration
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
