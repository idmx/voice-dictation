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
        with (
            patch(
                "voice_dictation.injection.macos_injector.subprocess.run",
                return_value=make_completed_process(),
            ) as mock_run,
            patch.object(MacOSTextInjector, "_simulate_cmd_v"),
            patch.dict("sys.modules", {"Quartz": mock_quartz}),
        ):
            injector.inject("test text")
        calls = mock_run.call_args_list
        written_inputs = [c.kwargs.get("input", "") for c in calls if "pbcopy" in c.args[0]]
        assert "test text" in written_inputs

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
