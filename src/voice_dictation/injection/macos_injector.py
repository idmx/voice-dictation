"""macOS text injector using clipboard or typing simulation."""

from __future__ import annotations

import os
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

# Time to wait after simulating Cmd+V before restoring the old clipboard.
# Must be long enough for the target app to read the clipboard content.
_PASTE_SETTLE_DELAY = 0.5


def _check_ax_enabled() -> bool:
    """Check if the app has Accessibility permissions on macOS.

    Uses AXIsProcessTrusted() which returns True only when the calling
    process has been granted Accessibility access.
    """
    try:
        from ApplicationServices import AXIsProcessTrusted

        return AXIsProcessTrusted()
    except Exception:
        return False


class MacOSTextInjector(TextInjector):
    """Inject text on macOS via clipboard paste or CGEvent typing."""

    def __init__(
        self,
        method: str = "clipboard",
        restore_clipboard: bool = True,
        paste_delay: float = 0.3,
    ) -> None:
        if method not in ("clipboard", "typing"):
            raise ValueError(f"Unknown injection method: {method!r}")
        self._method = method
        self._restore_clipboard = restore_clipboard
        self._paste_delay = paste_delay
        self._clipboard = ClipboardManager()
        self._ax_checked = False
        self._ax_enabled = False

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

    def _check_accessibility_once(self) -> None:
        """Log a one-time warning if Accessibility is not granted."""
        if self._ax_checked:
            return
        self._ax_checked = True
        self._ax_enabled = _check_ax_enabled()
        if self._ax_enabled:
            logger.info("Accessibility permissions: granted")
        else:
            logger.warning(
                "Accessibility permissions NOT granted — "
                "text paste (Cmd+V) will NOT work. "
                "Grant access in System Settings > Privacy & Security > "
                "Accessibility for Voice Dictation."
            )

    def _inject_via_clipboard(self, text: str) -> None:
        self._check_accessibility_once()

        if self._restore_clipboard:
            self._clipboard.save()

        self._write_clipboard(text)
        logger.info(f"Text written to clipboard ({len(text)} chars)")

        paste_ok = self._simulate_cmd_v()

        if paste_ok:
            # Wait for the target app to read the clipboard before we
            # overwrite it with the old content.
            time.sleep(self._paste_delay + _PASTE_SETTLE_DELAY)
            if self._restore_clipboard:
                try:
                    self._clipboard.restore()
                except Exception as exc:
                    logger.warning(f"Clipboard restore failed (graceful): {exc}")
        else:
            # Paste failed — do NOT restore the old clipboard content.
            # Keep the transcribed text on the clipboard so the user
            # can manually press Cmd+V to paste it.
            logger.info(
                "Paste may have failed — text remains on clipboard. "
                "Press Cmd+V to paste manually."
            )

    def _inject_via_typing(self, text: str) -> None:
        self._check_accessibility_once()
        quartz = self._import_quartz()
        for char in text:
            event_down = quartz.CGEventCreateKeyboardEvent(None, 0, True)
            quartz.CGEventKeyboardSetUnicodeString(event_down, len(char), char)
            quartz.CGEventPost(_KCGHIDEVENTTAP, event_down)

            event_up = quartz.CGEventCreateKeyboardEvent(None, 0, False)
            quartz.CGEventKeyboardSetUnicodeString(event_up, len(char), char)
            quartz.CGEventPost(_KCGHIDEVENTTAP, event_up)

        logger.debug(f"Typed {len(text)} characters via CGEvent")

    def _simulate_cmd_v(self) -> bool:
        """Simulate Cmd+V paste.

        Tries AppleScript first, then CGEvent fallback.
        CGEvent is dispatched to the main thread via dispatch_async,
        because CGEventPost from a background thread may not be delivered
        to the focused application on macOS.
        Returns True if paste likely succeeded, False otherwise.
        """
        # Try AppleScript (requires Accessibility for osascript)
        # Use "key code 9" instead of keystroke "v" to avoid layout issues:
        # keystroke "v" sends the letter v from the CURRENT keyboard layout,
        # which is "м" in Russian layout — resulting in Cmd+М instead of Cmd+V.
        # Key code 9 always refers to the physical V key regardless of layout.
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to key code 9 using command down',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info("Simulated Cmd+V via AppleScript")
                return True
            logger.debug(
                f"AppleScript Cmd+V failed (rc={result.returncode}): "
                f"{result.stderr.strip()}"
            )
        except FileNotFoundError:
            logger.debug("osascript not found, falling back to CGEvent")
        except subprocess.TimeoutExpired:
            logger.debug("osascript timed out, falling back to CGEvent")
        except Exception as exc:
            logger.debug(f"AppleScript Cmd+V error: {exc}, falling back to CGEvent")

        # Fallback: CGEvent on the main thread (requires Accessibility)
        try:
            self._post_cmd_v_on_main_thread()
            logger.info("Simulated Cmd+V via CGEvent on main thread")
            return self._ax_enabled
        except Exception as exc:
            logger.error(f"CGEvent Cmd+V also failed: {exc}")
            return False

    @staticmethod
    def _post_cmd_v_on_main_thread() -> None:
        """Post Cmd+V CGEvent on the main thread via PyObjC dispatch."""
        import threading

        done = threading.Event()

        def _do_post() -> None:
            try:
                quartz = MacOSTextInjector._import_quartz()
                v_down = quartz.CGEventCreateKeyboardEvent(
                    None, _CMD_V_KEYCODE, True
                )
                quartz.CGEventSetFlags(v_down, _KCGEVENTFLAGMASKCOMMAND)
                quartz.CGEventPost(_KCGHIDEVENTTAP, v_down)

                v_up = quartz.CGEventCreateKeyboardEvent(
                    None, _CMD_V_KEYCODE, False
                )
                quartz.CGEventSetFlags(v_up, _KCGEVENTFLAGMASKCOMMAND)
                quartz.CGEventPost(_KCGHIDEVENTTAP, v_up)
            except Exception as exc:
                logger.error(f"Error in CGEvent post: {exc}")
            finally:
                done.set()

        # Use PyObjC dispatch to schedule on the main queue.
        # This is the reliable way to run code on the main thread
        # on macOS — ctypes dlsym does not find dispatch symbols.
        try:
            from Foundation import (
                NSOperationQueue,
            )

            main_queue = NSOperationQueue.mainQueue()
            main_queue.addOperationWithBlock_(_do_post)
            done.wait(timeout=3.0)
            if done.is_set():
                logger.debug("CGEvent Cmd+V posted via NSOperationQueue mainQueue")
            else:
                logger.warning("NSOperationQueue dispatch timed out")
        except ImportError:
            logger.debug("Foundation not available, running CGEvent directly")
            _do_post()
        except Exception as exc:
            logger.debug(f"NSOperationQueue dispatch failed ({exc}), running directly")
            _do_post()

    @staticmethod
    def _write_clipboard(text: str) -> None:
        try:
            env = {**os.environ, "LANG": "en_US.UTF-8"}
            proc = subprocess.Popen(
                ["pbcopy"],
                env=env,
                stdin=subprocess.PIPE,
            )
            proc.communicate(input=text.encode("utf-8"), timeout=5)
            if proc.returncode != 0:
                raise InjectionError(f"pbcopy failed with code {proc.returncode}")
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
