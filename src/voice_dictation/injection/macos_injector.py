"""macOS text injector using clipboard or typing simulation."""

import subprocess
import time
from typing import Any

from loguru import logger

from voice_dictation.core.exceptions import InjectionError
from voice_dictation.injection.base import TextInjector
from voice_dictation.utils.clipboard import ClipboardManager

_CMD_V_KEYCODE = 9
_KCGEVENTFLAGMASKCOMMAND = 1 << 20
_KCGHIDEVENTTAP = 0


class MacOSTextInjector(TextInjector):
    """Inject text on macOS via clipboard paste or CGEvent typing."""

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
        self._simulate_cmd_v()
        time.sleep(self._paste_delay)

        if self._restore_clipboard:
            try:
                self._clipboard.restore()
            except Exception as exc:
                logger.warning(f"Clipboard restore failed (graceful): {exc}")

    def _inject_via_typing(self, text: str) -> None:
        quartz = self._import_quartz()
        for char in text:
            event_down = quartz.CGEventCreateKeyboardEvent(None, 0, True)
            quartz.CGEventKeyboardSetUnicodeString(event_down, len(char), char)
            quartz.CGEventPost(_KCGHIDEVENTTAP, event_down)

            event_up = quartz.CGEventCreateKeyboardEvent(None, 0, False)
            quartz.CGEventKeyboardSetUnicodeString(event_up, len(char), char)
            quartz.CGEventPost(_KCGHIDEVENTTAP, event_up)

        logger.debug(f"Typed {len(text)} characters via CGEvent")

    def _simulate_cmd_v(self) -> None:
        quartz = self._import_quartz()
        v_down = quartz.CGEventCreateKeyboardEvent(None, _CMD_V_KEYCODE, True)
        quartz.CGEventSetFlags(v_down, _KCGEVENTFLAGMASKCOMMAND)
        quartz.CGEventPost(_KCGHIDEVENTTAP, v_down)

        v_up = quartz.CGEventCreateKeyboardEvent(None, _CMD_V_KEYCODE, False)
        quartz.CGEventSetFlags(v_up, _KCGEVENTFLAGMASKCOMMAND)
        quartz.CGEventPost(_KCGHIDEVENTTAP, v_up)
        logger.debug("Simulated Cmd+V")

    @staticmethod
    def _write_clipboard(text: str) -> None:
        try:
            result = subprocess.run(
                ["pbcopy"],
                input=text,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise InjectionError(f"pbcopy failed with code {result.returncode}")
        except FileNotFoundError as exc:
            raise InjectionError(f"pbcopy not found: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise InjectionError(f"pbcopy timed out: {exc}") from exc

    @staticmethod
    def _import_quartz() -> Any:
        try:
            import Quartz

            return Quartz
        except ImportError as exc:
            raise InjectionError("Quartz framework not available (macOS only)") from exc
