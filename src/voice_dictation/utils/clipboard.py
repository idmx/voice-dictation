"""Cross-platform clipboard save/restore."""

import subprocess
from pathlib import Path

from loguru import logger

from voice_dictation.core.exceptions import ClipboardError
from voice_dictation.platform.detect import is_macos, is_windows


class ClipboardManager:
    """Save and restore clipboard content across platforms."""

    def __init__(self, restore_timeout: float = 2.0) -> None:
        self._restore_timeout = restore_timeout
        self._saved_text: str | None = None
        self._saved_clipboard_available = False

    def save(self) -> None:
        """Save current clipboard content."""
        try:
            self._saved_text = self._read_clipboard()
            self._saved_clipboard_available = True
            logger.debug("Clipboard content saved")
        except Exception as e:
            logger.warning(f"Could not read clipboard: {e}")
            self._saved_text = None
            self._saved_clipboard_available = False

    def restore(self) -> None:
        """Restore previously saved clipboard content."""
        if not self._saved_clipboard_available:
            logger.debug("No saved clipboard content to restore")
            return

        try:
            if self._saved_text is not None:
                self._write_clipboard(self._saved_text)
                logger.debug("Clipboard content restored")
            else:
                self._clear_clipboard()
                logger.debug("Clipboard cleared (was empty before)")
        except ClipboardError:
            self._save_to_file_fallback()
        except Exception as e:
            logger.error(f"Failed to restore clipboard: {e}")
            self._save_to_file_fallback()

    def _read_clipboard(self) -> str | None:
        """Read text from the system clipboard."""
        if is_macos():
            return self._read_clipboard_macos()
        elif is_windows():
            return self._read_clipboard_windows()
        else:
            return self._read_clipboard_linux()

    def _write_clipboard(self, text: str) -> None:
        """Write text to the system clipboard."""
        if is_macos():
            self._write_clipboard_macos(text)
        elif is_windows():
            self._write_clipboard_windows(text)
        else:
            self._write_clipboard_linux(text)

    def _clear_clipboard(self) -> None:
        """Clear the system clipboard."""
        self._write_clipboard("")

    @staticmethod
    def _read_clipboard_macos() -> str | None:
        try:
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise ClipboardError(f"Failed to read macOS clipboard: {e}") from e

    @staticmethod
    def _write_clipboard_macos(text: str) -> None:
        try:
            result = subprocess.run(
                ["pbcopy"],
                input=text,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise ClipboardError(f"pbcopy failed with code {result.returncode}")
        except subprocess.TimeoutExpired as e:
            raise ClipboardError(f"pbcopy timed out: {e}") from e
        except FileNotFoundError as e:
            raise ClipboardError(f"pbcopy not found: {e}") from e

    @staticmethod
    def _read_clipboard_windows() -> str | None:
        try:
            import win32clipboard  # type: ignore
            import win32con  # type: ignore

            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                    data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                    return data
                return None
            finally:
                win32clipboard.CloseClipboard()
        except ImportError:
            raise ClipboardError("win32clipboard not available") from None
        except Exception as e:
            raise ClipboardError(f"Failed to read Windows clipboard: {e}") from e

    @staticmethod
    def _write_clipboard_windows(text: str) -> None:
        try:
            import win32clipboard  # type: ignore
            import win32con  # type: ignore

            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()
        except ImportError:
            raise ClipboardError("win32clipboard not available") from None
        except Exception as e:
            raise ClipboardError(f"Failed to write Windows clipboard: {e}") from e

    @staticmethod
    def _read_clipboard_linux() -> str | None:
        try:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise ClipboardError(f"Failed to read Linux clipboard: {e}") from e

    @staticmethod
    def _write_clipboard_linux(text: str) -> None:
        try:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise ClipboardError(f"xclip failed with code {result.returncode}")
        except subprocess.TimeoutExpired as e:
            raise ClipboardError(f"xclip timed out: {e}") from e
        except FileNotFoundError as e:
            raise ClipboardError(f"xclip not found: {e}") from e

    def _save_to_file_fallback(self) -> None:
        """Save clipboard content to a file when restoration fails."""
        if self._saved_text is None:
            return

        try:
            fallback_dir = Path.home() / ".voice-dictation" / "clipboard_backup"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            fallback_file = fallback_dir / "clipboard_backup.txt"
            fallback_file.write_text(self._saved_text, encoding="utf-8")
            logger.info(f"Clipboard content saved to fallback file: {fallback_file}")
        except Exception as e:
            logger.error(f"Failed to save clipboard to fallback file: {e}")
