"""Unit tests for Windows text injector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from voice_dictation.core.exceptions import InjectionError
from voice_dictation.injection.windows_injector import WindowsTextInjector


@pytest.fixture
def mock_user32() -> MagicMock:
    user32 = MagicMock()
    user32.SendInput = MagicMock(return_value=1)
    return user32


@pytest.fixture
def mock_windll(mock_user32: MagicMock) -> MagicMock:
    windll = MagicMock()
    windll.user32 = mock_user32
    return windll


@pytest.fixture
def mock_win32clipboard() -> MagicMock:
    win32clipboard = MagicMock()
    return win32clipboard


@pytest.fixture
def mock_win32con() -> MagicMock:
    win32con = MagicMock()
    win32con.CF_UNICODETEXT = 13
    return win32con


@pytest.fixture
def injector(
    mock_windll: MagicMock,
    mock_win32clipboard: MagicMock,
    mock_win32con: MagicMock,
) -> WindowsTextInjector:
    with (
        patch(
            "voice_dictation.injection.windows_injector.ctypes.windll",
            mock_windll,
            create=True,
        ),
        patch.dict(
            "sys.modules",
            {
                "win32clipboard": mock_win32clipboard,
                "win32con": mock_win32con,
            },
        ),
    ):
        return WindowsTextInjector(method="clipboard", paste_delay=0)


@pytest.fixture
def typing_injector(
    mock_windll: MagicMock,
    mock_win32clipboard: MagicMock,
    mock_win32con: MagicMock,
) -> WindowsTextInjector:
    with (
        patch(
            "voice_dictation.injection.windows_injector.ctypes.windll",
            mock_windll,
            create=True,
        ),
        patch.dict(
            "sys.modules",
            {
                "win32clipboard": mock_win32clipboard,
                "win32con": mock_win32con,
            },
        ),
    ):
        return WindowsTextInjector(method="typing", paste_delay=0)


class TestClipboardInject:
    def test_clipboard_inject_ctrl_v(
        self,
        injector: WindowsTextInjector,
        mock_user32: MagicMock,
        mock_win32clipboard: MagicMock,
        mock_win32con: MagicMock,
    ) -> None:
        mock_cm = MagicMock()
        injector._clipboard = mock_cm
        with (
            patch(
                "voice_dictation.injection.windows_injector.ctypes.windll",
                create=True,
            ) as windll_mock,
            patch.object(WindowsTextInjector, "_write_clipboard"),
            patch.dict(
                "sys.modules",
                {
                    "win32clipboard": mock_win32clipboard,
                    "win32con": mock_win32con,
                },
            ),
        ):
            windll_mock.user32.SendInput = mock_user32.SendInput
            injector.inject("hello")
        assert mock_user32.SendInput.call_count == 1
        args = mock_user32.SendInput.call_args
        n_inputs = args.args[0]
        assert n_inputs == 4

    def test_clipboard_unicode_text(
        self,
        injector: WindowsTextInjector,
        mock_win32clipboard: MagicMock,
        mock_win32con: MagicMock,
        mock_user32: MagicMock,
    ) -> None:
        mock_cm = MagicMock()
        injector._clipboard = mock_cm
        with (
            patch.object(WindowsTextInjector, "_simulate_ctrl_v"),
            patch.dict(
                "sys.modules",
                {
                    "win32clipboard": mock_win32clipboard,
                    "win32con": mock_win32con,
                },
            ),
        ):
            injector.inject("Привет")
        mock_win32clipboard.OpenClipboard.assert_called_once()
        mock_win32clipboard.EmptyClipboard.assert_called_once()
        mock_win32clipboard.SetClipboardData.assert_called_once_with(13, "Привет")
        mock_win32clipboard.CloseClipboard.assert_called_once()

    def test_clipboard_restore(
        self,
        injector: WindowsTextInjector,
        mock_win32clipboard: MagicMock,
        mock_win32con: MagicMock,
        mock_user32: MagicMock,
    ) -> None:
        mock_cm = MagicMock()
        injector._clipboard = mock_cm
        with (
            patch.object(WindowsTextInjector, "_write_clipboard"),
            patch.object(WindowsTextInjector, "_simulate_ctrl_v"),
        ):
            injector.inject("hello")
        mock_cm.save.assert_called_once()
        mock_cm.restore.assert_called_once()

    def test_clipboard_inject_with_restore_disabled(
        self,
        mock_windll: MagicMock,
        mock_win32clipboard: MagicMock,
        mock_win32con: MagicMock,
    ) -> None:
        with (
            patch(
                "voice_dictation.injection.windows_injector.ctypes.windll",
                mock_windll,
                create=True,
            ),
            patch.dict(
                "sys.modules",
                {
                    "win32clipboard": mock_win32clipboard,
                    "win32con": mock_win32con,
                },
            ),
        ):
            inj = WindowsTextInjector(method="clipboard", restore_clipboard=False, paste_delay=0)
        mock_cm = MagicMock()
        inj._clipboard = mock_cm
        with (
            patch.object(WindowsTextInjector, "_write_clipboard"),
            patch.object(WindowsTextInjector, "_simulate_ctrl_v"),
        ):
            inj.inject("hello")
        mock_cm.save.assert_not_called()
        mock_cm.restore.assert_not_called()


class TestTypingInject:
    def test_typing_inject_send_input(
        self,
        typing_injector: WindowsTextInjector,
        mock_user32: MagicMock,
    ) -> None:
        with patch(
            "voice_dictation.injection.windows_injector.ctypes.windll",
            create=True,
        ) as windll_mock:
            windll_mock.user32.SendInput = mock_user32.SendInput
            typing_injector.inject("ab")
        assert mock_user32.SendInput.call_count == 1
        args = mock_user32.SendInput.call_args
        n_inputs = args.args[0]
        assert n_inputs == 4

    def test_typing_russian_text(
        self,
        typing_injector: WindowsTextInjector,
        mock_user32: MagicMock,
    ) -> None:
        with patch(
            "voice_dictation.injection.windows_injector.ctypes.windll",
            create=True,
        ) as windll_mock:
            windll_mock.user32.SendInput = mock_user32.SendInput
            typing_injector.inject("Привет")
        assert mock_user32.SendInput.call_count == 1
        args = mock_user32.SendInput.call_args
        n_inputs = args.args[0]
        assert n_inputs == len("Привет") * 2

    def test_typing_inject_multiline(
        self,
        typing_injector: WindowsTextInjector,
        mock_user32: MagicMock,
    ) -> None:
        text = "line1\nline2"
        with patch(
            "voice_dictation.injection.windows_injector.ctypes.windll",
            create=True,
        ) as windll_mock:
            windll_mock.user32.SendInput = mock_user32.SendInput
            typing_injector.inject(text)
        args = mock_user32.SendInput.call_args
        n_inputs = args.args[0]
        assert n_inputs == len(text) * 2


class TestEdgeCases:
    def test_inject_empty_string(
        self,
        injector: WindowsTextInjector,
        mock_user32: MagicMock,
    ) -> None:
        mock_cm = MagicMock()
        injector._clipboard = mock_cm
        injector.inject("")
        mock_cm.save.assert_not_called()
        mock_user32.SendInput.assert_not_called()

    def test_inject_raises_on_sendinput_error(
        self,
        typing_injector: WindowsTextInjector,
        mock_user32: MagicMock,
    ) -> None:
        mock_user32.SendInput.return_value = 0
        with (
            patch(
                "voice_dictation.injection.windows_injector.ctypes.windll",
                create=True,
            ) as windll_mock,
            pytest.raises(InjectionError),
        ):
            windll_mock.user32.SendInput = mock_user32.SendInput
            typing_injector.inject("a")

    def test_inject_logs_operation(
        self,
        typing_injector: WindowsTextInjector,
        mock_user32: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with patch(
            "voice_dictation.injection.windows_injector.ctypes.windll",
            create=True,
        ) as windll_mock:
            windll_mock.user32.SendInput = mock_user32.SendInput
            typing_injector.inject("test")
