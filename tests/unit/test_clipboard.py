"""Unit tests for clipboard save/restore."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from voice_dictation.utils.clipboard import ClipboardManager


def make_completed_process(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def macos_patches():
    return (
        patch(
            "voice_dictation.utils.clipboard.is_macos",
            return_value=True,
        ),
        patch(
            "voice_dictation.utils.clipboard.is_windows",
            return_value=False,
        ),
    )


class TestSaveClipboardText:
    """Save text clipboard."""

    def test_save_clipboard_text(self) -> None:
        cm = ClipboardManager()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process("hello world"),
            ),
        ):
            cm.save()
            assert cm._saved_text == "hello world"
            assert cm._saved_clipboard_available is True

    def test_save_empty_clipboard(self) -> None:
        cm = ClipboardManager()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process(""),
            ),
        ):
            cm.save()
            assert cm._saved_text == ""
            assert cm._saved_clipboard_available is True

    def test_save_clipboard_failure_graceful(self) -> None:
        cm = ClipboardManager()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                side_effect=FileNotFoundError("no pbpaste"),
            ),
        ):
            cm.save()
            assert cm._saved_clipboard_available is False


class TestSaveClipboardImage:
    """Save image clipboard (falls back to text-only; no crash)."""

    def test_save_clipboard_image(self) -> None:
        cm = ClipboardManager()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process(""),
            ),
        ):
            cm.save()
            assert cm._saved_clipboard_available is True


class TestRestoreClipboardText:
    """Restore saved text."""

    def test_restore_clipboard_text(self) -> None:
        cm = ClipboardManager()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process("original text"),
            ),
        ):
            cm.save()

        p_mac2, p_win2 = macos_patches()
        with (
            p_mac2,
            p_win2,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process(),
            ) as mock_run,
        ):
            cm.restore()
            assert mock_run.called

    def test_restore_when_nothing_saved(self) -> None:
        cm = ClipboardManager()
        with patch("voice_dictation.utils.clipboard.subprocess.run") as mock_run:
            cm.restore()
            assert not mock_run.called


class TestRestoreClipboardImage:
    """Restore image clipboard (text path, graceful)."""

    def test_restore_clipboard_image(self) -> None:
        cm = ClipboardManager()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process(""),
            ),
        ):
            cm.save()

        p_mac2, p_win2 = macos_patches()
        with (
            p_mac2,
            p_win2,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process(),
            ),
        ):
            cm.restore()


class TestRestoreAfterTimeout:
    """Timeout during restore -> graceful handling."""

    def test_restore_after_timeout(self) -> None:
        cm = ClipboardManager()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process("data"),
            ),
        ):
            cm.save()

        p_mac2, p_win2 = macos_patches()
        with (
            p_mac2,
            p_win2,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["pbcopy"], timeout=5),
            ),
        ):
            cm.restore()


class TestConcurrentClipboardAccess:
    """Another app changes clipboard -> no crash."""

    def test_concurrent_clipboard_access(self) -> None:
        cm = ClipboardManager()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process("first"),
            ),
        ):
            cm.save()

        p_mac2, p_win2 = macos_patches()
        with (
            p_mac2,
            p_win2,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                side_effect=[make_completed_process("changed by other app")],
            ),
        ):
            cm.restore()


class TestClipboardSaveRestoreRoundtrip:
    """save -> modify -> restore -> matches original."""

    def test_clipboard_save_restore_roundtrip(self) -> None:
        cm = ClipboardManager()
        written: list[str] = []

        def mock_run(args, **kwargs):
            if "pbpaste" in args:
                return make_completed_process("original content")
            if "pbcopy" in args:
                written.append(kwargs.get("input", ""))
                return make_completed_process()
            return make_completed_process()

        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                side_effect=mock_run,
            ),
        ):
            cm.save()
            assert cm._saved_text == "original content"

        p_mac2, p_win2 = macos_patches()
        with (
            p_mac2,
            p_win2,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                side_effect=mock_run,
            ),
        ):
            cm.restore()

        assert "original content" in written


class TestClipboardErrorHandling:
    """System API fails -> ClipboardError (internally handled)."""

    def test_clipboard_error_handling(self) -> None:
        cm = ClipboardManager()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                side_effect=FileNotFoundError("no pbcopy"),
            ),
        ):
            cm.save()
            assert cm._saved_clipboard_available is False


class TestClipboardWindows:
    """Windows clipboard path (mocked)."""

    @pytest.mark.windows
    def test_save_clipboard_windows(self) -> None:
        mock_clip = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13
        mock_clip.IsClipboardFormatAvailable.return_value = True
        mock_clip.GetClipboardData.return_value = "win text"

        cm = ClipboardManager()
        with (
            patch(
                "voice_dictation.utils.clipboard.is_macos",
                return_value=False,
            ),
            patch(
                "voice_dictation.utils.clipboard.is_windows",
                return_value=True,
            ),
            patch.dict(
                "sys.modules",
                {"win32clipboard": mock_clip, "win32con": mock_con},
            ),
        ):
            cm.save()
            assert cm._saved_text == "win text"

    @pytest.mark.windows
    def test_restore_clipboard_windows(self) -> None:
        mock_clip = MagicMock()
        mock_con = MagicMock()
        mock_con.CF_UNICODETEXT = 13

        cm = ClipboardManager()
        with (
            patch(
                "voice_dictation.utils.clipboard.is_macos",
                return_value=False,
            ),
            patch(
                "voice_dictation.utils.clipboard.is_windows",
                return_value=True,
            ),
            patch.dict(
                "sys.modules",
                {"win32clipboard": mock_clip, "win32con": mock_con},
            ),
        ):
            cm._saved_text = "win restore"
            cm._saved_clipboard_available = True
            cm.restore()
            mock_clip.SetClipboardData.assert_called_once_with(13, "win restore")
