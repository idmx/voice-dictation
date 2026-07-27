"""Integration tests for text injection pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from voice_dictation.injection.macos_injector import MacOSTextInjector


@pytest.fixture
def mock_quartz() -> MagicMock:
    quartz = MagicMock()
    quartz.kCGEventFlagMaskCommand = 1 << 20
    quartz.kCGHIDEventTap = 0
    return quartz


@pytest.fixture
def mock_field() -> MagicMock:
    field = MagicMock()
    field.received_text = ""

    def capture_paste(*args, **kwargs):
        pass

    field.capture_paste = capture_paste
    return field


@pytest.mark.integration
class TestTextInjectionIntegration:
    def test_inject_into_mock_field(self, mock_quartz: MagicMock, mock_field: MagicMock) -> None:
        received: list[str] = []

        def fake_write(text: str) -> None:
            received.append(text)

        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            inj = MacOSTextInjector(method="clipboard", paste_delay=0)
        mock_cm = MagicMock()
        inj._clipboard = mock_cm
        with (
            patch.object(MacOSTextInjector, "_write_clipboard", side_effect=fake_write),
            patch.object(MacOSTextInjector, "_simulate_cmd_v"),
        ):
            inj.inject("injected text")
        assert "injected text" in received
        mock_cm.save.assert_called_once()
        mock_cm.restore.assert_called_once()

    def test_inject_preserves_focus(self, mock_quartz: MagicMock) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            inj = MacOSTextInjector(method="typing", paste_delay=0)
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            inj.inject("focus test")
        assert mock_quartz.CGEventPost.call_count > 0

    def test_inject_unicode_chars(self, mock_quartz: MagicMock) -> None:
        written: list[str] = []

        def fake_write(text: str) -> None:
            written.append(text)

        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            inj = MacOSTextInjector(method="clipboard", paste_delay=0)
        mock_cm = MagicMock()
        inj._clipboard = mock_cm
        with (
            patch.object(MacOSTextInjector, "_write_clipboard", side_effect=fake_write),
            patch.object(MacOSTextInjector, "_simulate_cmd_v"),
        ):
            inj.inject("Привет, мир! Здравствуй!")
        assert written == ["Привет, мир! Здравствуй!"]

    def test_rapid_injections(self, mock_quartz: MagicMock) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            inj = MacOSTextInjector(method="typing", paste_delay=0)
        for i in range(3):
            with patch.dict("sys.modules", {"Quartz": mock_quartz}):
                inj.inject(f"text {i}")

    def test_clipboard_method_vs_typing(self, mock_quartz: MagicMock) -> None:
        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            cb_inj = MacOSTextInjector(method="clipboard", paste_delay=0)
            ty_inj = MacOSTextInjector(method="typing", paste_delay=0)
        cb_cm = MagicMock()
        cb_inj._clipboard = cb_cm
        with (
            patch.object(MacOSTextInjector, "_write_clipboard"),
            patch.object(MacOSTextInjector, "_simulate_cmd_v"),
            patch.dict("sys.modules", {"Quartz": mock_quartz}),
        ):
            cb_inj.inject("clipboard test")

        with patch.dict("sys.modules", {"Quartz": mock_quartz}):
            ty_inj.inject("typing test")
        assert cb_cm.restore.called
        assert mock_quartz.CGEventPost.call_count > 0
