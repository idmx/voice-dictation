"""Unit tests for PynputListener module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from voice_dictation.hotkey.pynput_listener import PynputListener


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
def fake_listener_factory():
    """Patch pynput Listener with a fake listener and return the factory."""
    instances: list[FakeListener] = []

    def factory(*args, **kwargs):
        inst = FakeListener(*args, **kwargs)
        instances.append(inst)
        return inst

    return factory, instances


@pytest.fixture
def patched_listener(mocker):
    """Patch pynput.keyboard.Listener and return collected instances."""
    instances: list[FakeListener] = []

    def factory(*args, **kwargs):
        inst = FakeListener(*args, **kwargs)
        instances.append(inst)
        return inst

    mocker.patch("pynput.keyboard.Listener", side_effect=factory)
    return instances


class TestHotkeyPressTriggersCallback:
    def test_hotkey_press_triggers_callback(self, patched_listener) -> None:
        on_activate = MagicMock()
        listener = PynputListener(mode="push_to_talk")
        listener.register("ctrl+shift+d", on_activate=on_activate)
        listener.start()

        assert len(patched_listener) == 1
        fake = patched_listener[0]

        # Simulate pressing ctrl, shift, d
        from pynput.keyboard import Key, KeyCode

        fake.on_press(Key.ctrl)
        fake.on_press(Key.shift)
        fake.on_press(KeyCode.from_char("d"))

        on_activate.assert_called_once()


class TestUnrelatedKeyIgnored:
    def test_unrelated_key_ignored(self, patched_listener) -> None:
        on_activate = MagicMock()
        listener = PynputListener(mode="push_to_talk")
        listener.register("ctrl+shift+d", on_activate=on_activate)
        listener.start()

        fake = patched_listener[0]
        from pynput.keyboard import Key, KeyCode

        # Press unrelated keys
        fake.on_press(Key.alt)
        fake.on_press(KeyCode.from_char("x"))

        on_activate.assert_not_called()


class TestRegisterMultipleHotkeys:
    def test_register_multiple_hotkeys(self, patched_listener) -> None:
        on_activate_1 = MagicMock()
        on_activate_2 = MagicMock()
        listener = PynputListener(mode="push_to_talk")
        listener.register("ctrl+d", on_activate=on_activate_1)
        listener.register("alt+f1", on_activate=on_activate_2)
        listener.start()

        fake = patched_listener[0]
        from pynput.keyboard import Key, KeyCode

        # Press ctrl+d -> triggers first callback
        fake.on_press(Key.ctrl)
        fake.on_press(KeyCode.from_char("d"))
        on_activate_1.assert_called_once()
        on_activate_2.assert_not_called()

        # Reset for next
        on_activate_1.reset_mock()

        # Release all and press alt+f1
        fake.on_release(Key.ctrl)
        fake.on_release(KeyCode.from_char("d"))
        fake.on_press(Key.alt)
        fake.on_press(Key.f1)
        on_activate_2.assert_called_once()
        on_activate_1.assert_not_called()


class TestPushToTalkMode:
    def test_push_to_talk_mode(self, patched_listener) -> None:
        on_activate = MagicMock()
        on_deactivate = MagicMock()
        listener = PynputListener(mode="push_to_talk")
        listener.register("ctrl+d", on_activate=on_activate, on_deactivate=on_deactivate)
        listener.start()

        fake = patched_listener[0]
        from pynput.keyboard import Key, KeyCode

        # Press ctrl then d -> activate
        fake.on_press(Key.ctrl)
        fake.on_press(KeyCode.from_char("d"))
        on_activate.assert_called_once()
        on_deactivate.assert_not_called()

        # Release d -> deactivate
        fake.on_release(KeyCode.from_char("d"))
        on_deactivate.assert_called_once()


class TestToggleMode:
    def test_toggle_mode(self, patched_listener) -> None:
        on_activate = MagicMock()
        on_deactivate = MagicMock()
        listener = PynputListener(mode="toggle")
        listener.register("ctrl+d", on_activate=on_activate, on_deactivate=on_deactivate)
        listener.start()

        fake = patched_listener[0]
        from pynput.keyboard import Key, KeyCode

        # First press -> activate
        fake.on_press(Key.ctrl)
        fake.on_press(KeyCode.from_char("d"))
        on_activate.assert_called_once()
        on_deactivate.assert_not_called()

        # Second press -> deactivate
        fake.on_release(KeyCode.from_char("d"))
        fake.on_press(KeyCode.from_char("d"))
        on_deactivate.assert_called_once()


class TestStartStopLifecycle:
    def test_start_stop_lifecycle(self, patched_listener) -> None:
        listener = PynputListener(mode="push_to_talk")
        listener.register("ctrl+d", on_activate=MagicMock())
        assert listener.is_running() is False

        listener.start()
        assert listener.is_running() is True

        listener.stop()
        assert listener.is_running() is False


class TestIsRunningInitiallyFalse:
    def test_is_running_initially_false(self) -> None:
        listener = PynputListener(mode="push_to_talk")
        assert listener.is_running() is False


class TestStopWhenNotStarted:
    def test_stop_when_not_started(self) -> None:
        listener = PynputListener(mode="push_to_talk")
        # Should not raise
        listener.stop()
        assert listener.is_running() is False


class TestDoubleStart:
    def test_double_start(self, patched_listener) -> None:
        listener = PynputListener(mode="push_to_talk")
        listener.register("ctrl+d", on_activate=MagicMock())

        listener.start()
        assert listener.is_running() is True
        assert len(patched_listener) == 1

        # Second start should be ignored
        listener.start()
        assert listener.is_running() is True
        assert len(patched_listener) == 1  # No new listener created


class TestCallbackExceptionDoesntCrashListener:
    def test_callback_exception_doesnt_crash_listener(self, patched_listener) -> None:
        def bad_callback() -> None:
            raise RuntimeError("Callback error")

        on_deactivate = MagicMock()
        listener = PynputListener(mode="push_to_talk")
        listener.register("ctrl+d", on_activate=bad_callback, on_deactivate=on_deactivate)
        listener.start()

        fake = patched_listener[0]
        from pynput.keyboard import Key, KeyCode

        # Trigger the bad callback - should not crash
        fake.on_press(Key.ctrl)
        fake.on_press(KeyCode.from_char("d"))

        # Listener should still be running
        assert listener.is_running() is True

        # Deactivate should still work
        fake.on_release(KeyCode.from_char("d"))
        on_deactivate.assert_called_once()


class TestPynputStartFailure:
    def test_pynput_start_failure(self, mocker) -> None:
        mocker.patch(
            "pynput.keyboard.Listener",
            side_effect=Exception("Permission denied"),
        )
        listener = PynputListener(mode="push_to_talk")
        listener.register("ctrl+d", on_activate=MagicMock())

        # Should not raise, just log error
        listener.start()
        assert listener.is_running() is False


class TestStopCleansUpState:
    def test_stop_cleans_up_state(self, patched_listener) -> None:
        listener = PynputListener(mode="push_to_talk")
        listener.register("ctrl+d", on_activate=MagicMock())
        listener.start()

        fake = patched_listener[0]
        from pynput.keyboard import Key, KeyCode

        # Press some keys
        fake.on_press(Key.ctrl)
        fake.on_press(KeyCode.from_char("d"))

        listener.stop()
        assert listener.is_running() is False
        assert fake.stopped is True


class TestOnlyModifierNoKey:
    def test_only_modifier_raises(self) -> None:
        from voice_dictation.core.exceptions import InvalidHotkeyError

        listener = PynputListener(mode="push_to_talk")
        with pytest.raises(InvalidHotkeyError):
            listener.register("ctrl", on_activate=MagicMock())


class TestPushToTalkPartialRelease:
    def test_push_to_talk_partial_release(self, patched_listener) -> None:
        on_activate = MagicMock()
        on_deactivate = MagicMock()
        listener = PynputListener(mode="push_to_talk")
        listener.register("ctrl+shift+d", on_activate=on_activate, on_deactivate=on_deactivate)
        listener.start()

        fake = patched_listener[0]
        from pynput.keyboard import Key, KeyCode

        # Press full combo
        fake.on_press(Key.ctrl)
        fake.on_press(Key.shift)
        fake.on_press(KeyCode.from_char("d"))
        on_activate.assert_called_once()

        # Release shift (part of combo) -> deactivate
        fake.on_release(Key.shift)
        on_deactivate.assert_called_once()
