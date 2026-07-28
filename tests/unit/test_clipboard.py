"""Unit tests for clipboard save/restore."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from voice_dictation.utils.clipboard import ClipboardManager


def make_completed_process(stdout: str | bytes = "", returncode: int = 0) -> subprocess.CompletedProcess:
    # _read_clipboard_macos uses binary mode (no text=True),
    # so stdout must be bytes
    if isinstance(stdout, str):
        stdout = stdout.encode("utf-8")
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=b"")


def make_mock_popen(returncode: int = 0) -> MagicMock:
    """Create a mock for subprocess.Popen used by _write_clipboard_macos."""
    mock = MagicMock()
    mock.communicate.return_value = (None, None)
    mock.returncode = returncode
    return mock


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
        mock_popen = make_mock_popen()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process("original text"),
            ),
            patch(
                "voice_dictation.utils.clipboard.subprocess.Popen",
                mock_popen,
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
            patch(
                "voice_dictation.utils.clipboard.subprocess.Popen",
                mock_popen,
            ),
        ):
            cm.restore()
            assert mock_popen.called

    def test_restore_when_nothing_saved(self) -> None:
        cm = ClipboardManager()
        with patch("voice_dictation.utils.clipboard.subprocess.run") as mock_run:
            cm.restore()
            assert not mock_run.called


class TestRestoreClipboardImage:
    """Restore image clipboard (text path, graceful)."""

    def test_restore_clipboard_image(self) -> None:
        cm = ClipboardManager()
        mock_popen = make_mock_popen()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process(""),
            ),
            patch(
                "voice_dictation.utils.clipboard.subprocess.Popen",
                mock_popen,
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
            patch(
                "voice_dictation.utils.clipboard.subprocess.Popen",
                mock_popen,
            ),
        ):
            cm.restore()


class TestRestoreAfterTimeout:
    """Timeout during restore -> graceful handling."""

    def test_restore_after_timeout(self) -> None:
        cm = ClipboardManager()
        mock_popen = make_mock_popen()
        mock_popen.communicate.side_effect = subprocess.TimeoutExpired(cmd=["pbcopy"], timeout=5)
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process("data"),
            ),
            patch(
                "voice_dictation.utils.clipboard.subprocess.Popen",
                mock_popen,
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
            patch(
                "voice_dictation.utils.clipboard.subprocess.Popen",
                mock_popen,
            ),
        ):
            cm.restore()


class TestConcurrentClipboardAccess:
    """Another app changes clipboard -> no crash."""

    def test_concurrent_clipboard_access(self) -> None:
        cm = ClipboardManager()
        mock_popen = make_mock_popen()
        p_mac, p_win = macos_patches()
        with (
            p_mac,
            p_win,
            patch(
                "voice_dictation.utils.clipboard.subprocess.run",
                return_value=make_completed_process("first"),
            ),
            patch(
                "voice_dictation.utils.clipboard.subprocess.Popen",
                mock_popen,
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
            patch(
                "voice_dictation.utils.clipboard.subprocess.Popen",
                mock_popen,
            ),
        ):
            cm.restore()


class TestClipboardSaveRestoreRoundtrip:
    """save -> modify -> restore -> matches original."""

    def test_clipboard_save_restore_roundtrip(self) -> None:
        cm = ClipboardManager()
        written: list[bytes] = []

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (None, None)

        def popen_factory(*args, **kwargs):
            # Track input passed to communicate
            original_communicate = mock_proc.communicate

            def tracking_communicate(*cargs, **ckwargs):
                input_data = ckwargs.get("input", cargs[0] if cargs else b"")
                written.append(input_data)
                return (None, None)

            mock_proc.communicate = tracking_communicate
            return mock_proc

        def mock_run(args, **kwargs):
            if "pbpaste" in args:
                return make_completed_process("original content")
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
            patch(
                "voice_dictation.utils.clipboard.subprocess.Popen",
                side_effect=popen_factory,
            ),
        ):
            cm.restore()

        assert b"original content" in written


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
