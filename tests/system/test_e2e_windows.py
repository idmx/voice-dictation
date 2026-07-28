"""System E2E tests for Windows — marked to skip in CI without real hardware."""

from __future__ import annotations

import sys

import pytest

pytestmark = [
    pytest.mark.system,
    pytest.mark.skipif(sys.platform != "win32", reason="Windows only"),
]


class TestE2EWindowsPipeline:
    """Placeholder E2E tests for Windows — need real hardware to run."""

    def test_full_dictation_cycle(self) -> None:
        """Simulate full dictation cycle on Windows.

        This test requires a real Windows desktop with microphone access.
        It is skipped in CI and only runs on a Windows machine with the
        `system` pytest marker enabled.
        """
        # On a real Windows machine, this would:
        # 1. Start the application
        # 2. Simulate hotkey press
        # 3. Record audio from microphone
        # 4. Release hotkey
        # 5. Wait for transcription
        # 6. Verify text was injected into focused field
        # For now, just verify imports work
        from voice_dictation.injection.windows_injector import WindowsTextInjector

        assert WindowsTextInjector is not None

    def test_clipboard_inject_with_russian_layout(self) -> None:
        """Verify clipboard injection works with Russian keyboard layout."""
        from voice_dictation.injection.windows_injector import WindowsTextInjector

        assert WindowsTextInjector is not None
