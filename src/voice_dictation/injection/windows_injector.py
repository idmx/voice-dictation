"""Windows text injector using clipboard or SendInput typing."""

import ctypes
import time
from ctypes import wintypes
from typing import Any

from loguru import logger

from voice_dictation.core.exceptions import InjectionError
from voice_dictation.injection.base import TextInjector
from voice_dictation.utils.clipboard import ClipboardManager

_VK_CONTROL = 0x11
_VK_V = 0x56
_INPUT_KEYBOARD = 1
_KEYEVENTF_UNICODE = 0x0004
_KEYEVENTF_KEYUP = 0x0002


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    )


class _InputUnion(ctypes.Union):
    _fields_ = (("ki", _KEYBDINPUT),)


class _INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("union", _InputUnion))


class WindowsTextInjector(TextInjector):
    """Inject text on Windows via clipboard paste or SendInput typing."""

    def __init__(
        self,
        method: str = "clipboard",
        restore_clipboard: bool = True,
        paste_delay: float = 0.1,
    ) -> None:
        if method not in ("clipboard", "typing"):
            raise ValueError(f"Unknown injection method: {method!r}")
        self._method = method
        self._restore_clipboard = restore_clipboard
        self._paste_delay = paste_delay
        self._clipboard = ClipboardManager()

    def inject(self, text: str) -> None:
        if not text:
            return
        try:
            if self._method == "clipboard":
                self._inject_via_clipboard(text)
            else:
                self._inject_via_typing(text)
        except InjectionError:
            raise
        except Exception as exc:
            raise InjectionError(f"Text injection failed: {exc}") from exc

    def _inject_via_clipboard(self, text: str) -> None:
        if self._restore_clipboard:
            self._clipboard.save()

        self._write_clipboard(text)
        self._simulate_ctrl_v()
        time.sleep(self._paste_delay)

        if self._restore_clipboard:
            try:
                self._clipboard.restore()
            except Exception as exc:
                logger.warning(f"Clipboard restore failed (graceful): {exc}")

    def _inject_via_typing(self, text: str) -> None:
        send_input = self._load_sendinput()
        inputs = []
        for char in text:
            scan = ord(char)
            inp_down = self._make_keyboard_input(scan, _KEYEVENTF_UNICODE)
            inp_up = self._make_keyboard_input(
                scan, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP
            )
            inputs.append(inp_down)
            inputs.append(inp_up)

        n = len(inputs)
        arr = (_INPUT * n)(*inputs)
        sent = send_input(n, ctypes.pointer(arr[0]), ctypes.sizeof(_INPUT))
        if sent == 0:
            raise InjectionError("SendInput returned 0 events")
        logger.debug(f"Typed {len(text)} characters via SendInput")

    def _simulate_ctrl_v(self) -> None:
        send_input = self._load_sendinput()
        inputs = [
            self._make_keyboard_input(_VK_CONTROL, 0),
            self._make_keyboard_input(_VK_V, 0),
            self._make_keyboard_input(_VK_V, _KEYEVENTF_KEYUP),
            self._make_keyboard_input(_VK_CONTROL, _KEYEVENTF_KEYUP),
        ]
        arr = (_INPUT * 4)(*inputs)
        sent = send_input(4, ctypes.pointer(arr[0]), ctypes.sizeof(_INPUT))
        if sent == 0:
            raise InjectionError("SendInput returned 0 events (Ctrl+V)")
        logger.debug("Simulated Ctrl+V")

    @staticmethod
    def _make_keyboard_input(scan: int, flags: int) -> "_INPUT":
        inp = _INPUT()
        inp.type = _INPUT_KEYBOARD
        inp.union.ki.wVk = 0
        inp.union.ki.wScan = scan
        inp.union.ki.dwFlags = flags
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = ctypes.pointer(wintypes.ULONG(0))
        return inp

    @staticmethod
    def _write_clipboard(text: str) -> None:
        win32clipboard, win32con = WindowsTextInjector._import_win32_clip()
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(
                    win32con.CF_UNICODETEXT, text
                )
            finally:
                win32clipboard.CloseClipboard()
        except Exception as exc:
            raise InjectionError(f"Failed to write Windows clipboard: {exc}") from exc

    @staticmethod
    def _load_sendinput() -> Any:
        try:
            return ctypes.windll.user32.SendInput
        except AttributeError as exc:
            raise InjectionError(
                "ctypes.windll not available (Windows only)"
            ) from exc

    @staticmethod
    def _import_win32_clip() -> tuple[Any, Any]:
        try:
            import win32clipboard  # type: ignore
            import win32con  # type: ignore
            return win32clipboard, win32con
        except ImportError as exc:
            raise InjectionError(
                "win32clipboard/win32con not available"
            ) from exc
