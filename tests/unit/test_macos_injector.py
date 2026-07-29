"""Unit tests for macOS text injector."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from voice_dictation.core.exceptions import InjectionError
from voice_dictation.injection.macos_injector import MacOSTextInjector


def make_completed_process(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


@pytest.fixture
def mock_quartz() -> MagicMock:
    quartz = MagicMock()
    quartz.kCGEventFlagMaskCommand = 1 << 20
    quartz.kCGHIDEventTap = 0
    return quartz


@pytest.fixture
def injector(mock_quartz: MagicMock) -> MacOSTextInjector:
    with patch.dict("sys.modules", {"Quartz": mock_quartz}):
        return MacOSTextInjector(method="clipboard", paste_delay=0)


@pytest.fixture
def typing_injector(mock_quartz: MagicMock) -> MacOSTextInjector:
    with patch.dict("sys.modules", {"Quartz": mock_quartz}):
        return MacOSTextInjector(method="typing", paste_delay=0)


class TestClipboardInject:
    def test_clipboard_inject_saves_existing(
        self, injector: MacOSTextInjector, mock_quartz: MagicMock
    ) -> None:
        mock_cm = MagicMock()
        injector._clipboard = mock_cm
        with (
            patch.object(MacOSTextInjector, "_write_clipboard"),
            patch.object(MacOSTextInjector, "_simulate_cmd_v"),
            patch.dict("sys.modules", {"Quartz": mock_quartz}),
        ):
            injector.inject("hello")
        mock_cm.save.assert_called_once()

    def test_clipboard_inject_writes_text(
        self, injector: MacOSTextInjector, mock_quartz: MagicMock
    ) -> None:
        mock_cm = MagicMock()
        injector._clipboard = mock_cm
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (None, None)
        mock_proc.returncode = 0
        with (
            patch(
                "voice_dictation.injection.macos_injector.subprocess.Popen",
                return_value=mock_proc,
            ),
            patch(
                "voice_dictation.injection.macos_injector.subprocess.run",
                return_value=make_completed_process(),
            ),
            patch.object(MacOSTextInjector, "_simulate_cmd_v"),
            patch.dict("sys.modules", {"Quartz": mock_quartz}),
        ):
            injector.inject("test text")
        # Verify Popen was called with pbcopy
        # Check communicate was called with UTF-8 encoded text
        comm_calls = mock_proc.communicate.call_args_list
        written_inputs = [c.kwargs.get("input", c.args[0] if c.args else b"") for c in comm_calls]
        assert b"test text" in written_inputs

    def test_clipboard_inject_simulates_cmd_v(
        self, injector: MacOSTextInjector, mock_quartz: MagicMock
    ) -> None:
        mock_cm = MagicMock()
        injector._clipboard = mock_cm
        with (
            patch.object(MacOSTextInjector, "_write_clipboard"),
            patch(
                "voice_dictation.injection.macos_injector.subprocess.run",
                return_value=make_completed_process(),
            ) as mock_run,
            patch.dict("sys.modules", {"Quartz": mock_quartz}),
        ):
            injector.inject("x")

        # osascript (AppleScript) is the primary Cmd+V method and succeeds,
        # so the CGEvent fallback should NOT be invoked.
        osascript_calls = [
            c for c in mock_run.call_args_list if c.args and "osascript" in c.args[0]
        ]
        assert len(osascript_calls) == 1
        assert any("command down" in arg for arg in osascript_calls[0].args[0])
        mock_quartz.CGEventCreateKeyboardEvent.assert_not_called()
        mock_quartz.CGEventPost.assert_not_called()

    def test_clipboard_inject_restores_buffer(
        self, injector: MacOSTextInjector, mock_quartz: MagicMock
    ) -> None:
        mock_cm = MagicMock()
        injector._clipboard = mock_cm
        with (
            patch.object(MacOSTextInjector, "_write_clipboard"),
            patch.object(MacOSTextInjector, "_simulate_cmd_v"),
            patch.dict("sys.modules", {"Quartz": mock_quartz}),
        ):
            injector.inject("hello")
        mock_cm.restore.assert_called_once()

    def test_clipboard_restore_failure(
        self, injector: MacOSTextInjector, mock_quartz: MagicMock
    ) -> None:
        mock_cm = MagicMock()
        mock_cm.restore.side_effect = RuntimeError("boom")
        injector._clipboard = mock_cm
        with (
            patch.object(MacOSTextInjector, "_write_clipboard"),
            patch.object(MacOSTextInjector, "_simulate_cmd_v"),
            patch.dict("sys.modules", {"Quartz": mock_quartz}),
        ):
            injector.inject("hello")
        mock_cm.restore.assert_called_once()

    def test_clipboard_inject_with_restore_disabled(self, mock_quartz: MagicMock) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            inj = MacOSTextInjector(method="clipboard", restore_clipboard=False, paste_delay=0)
        mock_cm = MagicMock()
        inj._clipboard = mock_cm
        with (
            patch.object(MacOSTextInjector, "_write_clipboard"),
            patch.object(MacOSTextInjector, "_simulate_cmd_v"),
            patch.dict("sys.modules", {"Quartz": mock_quartz}),
        ):
            inj.inject("hello")
        mock_cm.save.assert_not_called()
        mock_cm.restore.assert_not_called()


class TestTypingInject:
    def test_typing_inject_sends_key_events(
        self, typing_injector: MacOSTextInjector, mock_quartz: MagicMock
    ) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            typing_injector.inject("ab")
        assert mock_quartz.CGEventCreateKeyboardEvent.call_count == 4
        assert mock_quartz.CGEventKeyboardSetUnicodeString.call_count == 4
        assert mock_quartz.CGEventPost.call_count == 4

    def test_typing_inject_handles_unicode(
        self, typing_injector: MacOSTextInjector, mock_quartz: MagicMock
    ) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            typing_injector.inject("Привет")
        assert mock_quartz.CGEventKeyboardSetUnicodeString.call_count == 12
        chars_set = [c.args[2] for c in mock_quartz.CGEventKeyboardSetUnicodeString.call_args_list]
        assert "П" in chars_set
        assert "р" in chars_set

    def test_typing_inject_post_keydown_keyup(
        self, typing_injector: MacOSTextInjector, mock_quartz: MagicMock
    ) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            typing_injector.inject("a")
        down_call = mock_quartz.CGEventCreateKeyboardEvent.call_args_list[0]
        up_call = mock_quartz.CGEventCreateKeyboardEvent.call_args_list[1]
        assert down_call.args[2] is True
        assert up_call.args[2] is False
        assert mock_quartz.CGEventPost.call_count == 2


class TestEdgeCases:
    def test_inject_empty_string(self, injector: MacOSTextInjector, mock_quartz: MagicMock) -> None:
        mock_cm = MagicMock()
        injector._clipboard = mock_cm
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            injector.inject("")
        mock_cm.save.assert_not_called()
        mock_quartz.CGEventPost.assert_not_called()

    def test_inject_multiline(
        self, typing_injector: MacOSTextInjector, mock_quartz: MagicMock
    ) -> None:
        text = "line1\nline2\nline3"
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            typing_injector.inject(text)
        assert mock_quartz.CGEventCreateKeyboardEvent.call_count == len(text) * 2

    def test_inject_raises_on_quartz_error(
        self, typing_injector: MacOSTextInjector, mock_quartz: MagicMock
    ) -> None:
        mock_quartz.CGEventPost.side_effect = RuntimeError("post failed")
        with (
            patch.dict("sys.modules", {"Quartz": mock_quartz}),
            pytest.raises(InjectionError),
        ):
            typing_injector.inject("a")

    def test_inject_logs_operation(
        self,
        typing_injector: MacOSTextInjector,
        mock_quartz: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            typing_injector.inject("test")


class TestSimulateCmdVFallback:
    """CGEvent fallback when osascript fails."""

    def test_cgevent_fallback_when_osascript_returns_nonzero(self, mock_quartz: MagicMock) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            injector = MacOSTextInjector(method="clipboard", paste_delay=0)
        with (
            patch(
                "voice_dictation.injection.macos_injector.subprocess.run",
                return_value=make_completed_process(returncode=1),
            ),
            patch.object(MacOSTextInjector, "_post_cmd_v_on_main_thread") as mock_post,
        ):
            result = injector._simulate_cmd_v()
            mock_post.assert_called_once()
            assert result is False


class TestSimulateCmdVOsascriptNotFound:
    """CGEvent fallback when osascript not found."""

    def test_cgevent_fallback_when_osascript_not_found(self, mock_quartz: MagicMock) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            injector = MacOSTextInjector(method="clipboard", paste_delay=0)
        with (
            patch(
                "voice_dictation.injection.macos_injector.subprocess.run",
                side_effect=FileNotFoundError("osascript not found"),
            ),
            patch.object(MacOSTextInjector, "_post_cmd_v_on_main_thread") as mock_post,
        ):
            injector._simulate_cmd_v()
            mock_post.assert_called_once()


class TestSimulateCmdVTimeout:
    """CGEvent fallback when osascript times out."""

    def test_cgevent_fallback_when_osascript_times_out(self, mock_quartz: MagicMock) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            injector = MacOSTextInjector(method="clipboard", paste_delay=0)
        with (
            patch(
                "voice_dictation.injection.macos_injector.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["osascript"], timeout=5),
            ),
            patch.object(MacOSTextInjector, "_post_cmd_v_on_main_thread") as mock_post,
        ):
            injector._simulate_cmd_v()
            mock_post.assert_called_once()


class TestWriteClipboardEnv:
    """_write_clipboard passes LANG env and UTF-8 encoding."""

    def test_write_clipboard_env_and_encoding(self) -> None:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (None, None)
        mock_proc.returncode = 0
        with patch(
            "voice_dictation.injection.macos_injector.subprocess.Popen",
            return_value=mock_proc,
        ) as mock_popen:
            MacOSTextInjector._write_clipboard("текст")
        env_arg = mock_popen.call_args.kwargs["env"]
        assert env_arg["LANG"] == "en_US.UTF-8"
        input_data = mock_proc.communicate.call_args.kwargs["input"]
        assert input_data == "текст".encode()


class TestPasteFailureNoRestore:
    """When paste fails, clipboard is NOT restored."""

    def test_paste_failure_does_not_restore_clipboard(self, mock_quartz: MagicMock) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            injector = MacOSTextInjector(method="clipboard", paste_delay=0)
        mock_cm = MagicMock()
        injector._clipboard = mock_cm
        with (
            patch.object(MacOSTextInjector, "_write_clipboard"),
            patch.object(MacOSTextInjector, "_simulate_cmd_v", return_value=False),
            patch.dict("sys.modules", {"Quartz": mock_quartz}),
        ):
            injector.inject("text")
        mock_cm.save.assert_called_once()
        mock_cm.restore.assert_not_called()


class TestCheckAccessibilityOnce:
    """_check_accessibility_once logs warning only once."""

    def test_check_accessibility_once_called_only_once(self, mock_quartz: MagicMock) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            injector = MacOSTextInjector(method="clipboard", paste_delay=0)
        with patch(
            "voice_dictation.injection.macos_injector._check_ax_enabled",
            return_value=False,
        ) as mock_check:
            injector._check_accessibility_once()
            injector._check_accessibility_once()
            mock_check.assert_called_once()
