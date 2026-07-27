"""Integration tests for hotkey to recording flow."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from voice_dictation.audio.base import AudioCapture
from voice_dictation.hotkey.pynput_listener import PynputListener


class MockAudioCapture(AudioCapture):
    """Mock audio capture for integration tests."""

    def __init__(self) -> None:
        self._recording = False
        self.start_called = 0
        self.stop_called = 0

    def start(self) -> None:
        self._recording = True
        self.start_called += 1

    def stop(self) -> np.ndarray:
        self._recording = False
        self.stop_called += 1
        return np.array([1, 2, 3], dtype=np.int16)

    def is_recording(self) -> bool:
        return self._recording


class FakeListener:
    """A fake pynput Listener for testing."""

    def __init__(self, on_press=None, on_release=None, **kwargs) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture
def patched_pynput_listener(mocker):
    """Patch pynput.keyboard.Listener and return collected instances."""
    instances: list[FakeListener] = []

    def factory(*args, **kwargs):
        inst = FakeListener(*args, **kwargs)
        instances.append(inst)
        return inst

    mocker.patch("pynput.keyboard.Listener", side_effect=factory)
    return instances


@pytest.fixture
def audio_capture():
    return MockAudioCapture()


def press_key(fake, key):
    fake.on_press(key)


def release_key(fake, key):
    fake.on_release(key)


class TestHotkeyStartsRecording:
    def test_hotkey_starts_recording(
        self, patched_pynput_listener, audio_capture
    ) -> None:
        listener = PynputListener(mode="push_to_talk")
        listener.register(
            "ctrl+d",
            on_activate=audio_capture.start,
            on_deactivate=audio_capture.stop,
        )
        listener.start()

        assert not audio_capture.is_recording()

        fake = patched_pynput_listener[0]
        from pynput.keyboard import Key, KeyCode

        press_key(fake, Key.ctrl)
        press_key(fake, KeyCode.from_char("d"))

        assert audio_capture.is_recording()
        assert audio_capture.start_called == 1
        listener.stop()


class TestHotkeyStopsRecording:
    def test_hotkey_stops_recording(
        self, patched_pynput_listener, audio_capture
    ) -> None:
        listener = PynputListener(mode="push_to_talk")
        captured_audio = []

        def on_deactivate():
            captured_audio.append(audio_capture.stop())

        listener.register(
            "ctrl+d",
            on_activate=audio_capture.start,
            on_deactivate=on_deactivate,
        )
        listener.start()

        fake = patched_pynput_listener[0]
        from pynput.keyboard import Key, KeyCode

        press_key(fake, Key.ctrl)
        press_key(fake, KeyCode.from_char("d"))
        assert audio_capture.is_recording()

        release_key(fake, KeyCode.from_char("d"))
        assert not audio_capture.is_recording()
        assert audio_capture.stop_called == 1
        assert len(captured_audio) == 1
        assert np.array_equal(captured_audio[0], np.array([1, 2, 3], dtype=np.int16))
        listener.stop()


class TestNoRecordingWithoutHotkey:
    def test_no_recording_without_hotkey(
        self, patched_pynput_listener, audio_capture
    ) -> None:
        listener = PynputListener(mode="push_to_talk")
        listener.register(
            "ctrl+d",
            on_activate=audio_capture.start,
            on_deactivate=audio_capture.stop,
        )
        listener.start()

        fake = patched_pynput_listener[0]
        from pynput.keyboard import Key, KeyCode

        # Press unrelated keys
        press_key(fake, Key.alt)
        press_key(fake, KeyCode.from_char("x"))

        assert not audio_capture.is_recording()
        assert audio_capture.start_called == 0
        listener.stop()


class TestToggleModeStartsAndStops:
    def test_toggle_mode_starts_and_stops(
        self, patched_pynput_listener, audio_capture
    ) -> None:
        listener = PynputListener(mode="toggle")
        listener.register(
            "ctrl+d",
            on_activate=audio_capture.start,
            on_deactivate=audio_capture.stop,
        )
        listener.start()

        fake = patched_pynput_listener[0]
        from pynput.keyboard import Key, KeyCode

        # First press -> start recording
        press_key(fake, Key.ctrl)
        press_key(fake, KeyCode.from_char("d"))
        assert audio_capture.is_recording()
        assert audio_capture.start_called == 1

        # Release and press again -> stop recording
        release_key(fake, KeyCode.from_char("d"))
        press_key(fake, KeyCode.from_char("d"))
        assert not audio_capture.is_recording()
        assert audio_capture.stop_called == 1
        listener.stop()


class TestHotkeyChangeReRegisters:
    def test_hotkey_change_re_registers(
        self, patched_pynput_listener, audio_capture
    ) -> None:
        listener = PynputListener(mode="push_to_talk")
        listener.register(
            "ctrl+d",
            on_activate=audio_capture.start,
            on_deactivate=audio_capture.stop,
        )
        listener.start()

        fake = patched_pynput_listener[0]
        from pynput.keyboard import Key, KeyCode

        # Old hotkey works
        press_key(fake, Key.ctrl)
        press_key(fake, KeyCode.from_char("d"))
        assert audio_capture.is_recording()
        release_key(fake, KeyCode.from_char("d"))
        assert not audio_capture.is_recording()

        listener.stop()

        # Re-register with new hotkey
        audio_capture2 = MockAudioCapture()
        listener2 = PynputListener(mode="push_to_talk")
        listener2.register(
            "alt+f5",
            on_activate=audio_capture2.start,
            on_deactivate=audio_capture2.stop,
        )
        listener2.start()

        fake2 = patched_pynput_listener[1]

        # Old hotkey (ctrl+d) should NOT trigger new capture
        press_key(fake2, Key.ctrl)
        press_key(fake2, KeyCode.from_char("d"))
        assert not audio_capture2.is_recording()

        # Release old keys
        release_key(fake2, Key.ctrl)
        release_key(fake2, KeyCode.from_char("d"))

        # New hotkey (alt+f5) should trigger
        press_key(fake2, Key.alt)
        press_key(fake2, Key.f5)
        assert audio_capture2.is_recording()
        listener2.stop()


class TestSpecialKeyHotkey:
    def test_function_key_hotkey(
        self, patched_pynput_listener, audio_capture
    ) -> None:
        listener = PynputListener(mode="push_to_talk")
        listener.register(
            "ctrl+f5",
            on_activate=audio_capture.start,
            on_deactivate=audio_capture.stop,
        )
        listener.start()

        fake = patched_pynput_listener[0]
        from pynput.keyboard import Key

        press_key(fake, Key.ctrl)
        press_key(fake, Key.f5)
        assert audio_capture.is_recording()

        release_key(fake, Key.f5)
        assert not audio_capture.is_recording()
        listener.stop()


class TestMultipleModifiersRecording:
    def test_three_modifier_combo(
        self, patched_pynput_listener, audio_capture
    ) -> None:
        listener = PynputListener(mode="push_to_talk")
        listener.register(
            "ctrl+alt+shift+t",
            on_activate=audio_capture.start,
            on_deactivate=audio_capture.stop,
        )
        listener.start()

        fake = patched_pynput_listener[0]
        from pynput.keyboard import Key, KeyCode

        # Press only two modifiers -> no activation
        press_key(fake, Key.ctrl)
        press_key(fake, Key.alt)
        press_key(fake, KeyCode.from_char("t"))
        assert not audio_capture.is_recording()

        # Now press all three
        press_key(fake, Key.shift)
        assert audio_capture.is_recording()

        # Release any modifier -> stop
        release_key(fake, Key.shift)
        assert not audio_capture.is_recording()
        listener.stop()
