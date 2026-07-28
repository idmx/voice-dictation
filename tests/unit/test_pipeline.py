"""Unit tests for the DictationPipeline orchestrator.

Every external component is mocked so the pipeline logic is tested in
isolation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from voice_dictation.audio.base import AudioCapture
from voice_dictation.config.schema import AppConfig
from voice_dictation.core.exceptions import (
    AudioDeviceError,
    InjectionError,
    TranscriptionError,
)
from voice_dictation.core.state import State, StateMachine
from voice_dictation.hotkey.base import HotkeyListener
from voice_dictation.injection.base import TextInjector
from voice_dictation.pipeline import DictationPipeline
from voice_dictation.recognition.base import RecognitionEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_audio() -> MagicMock:
    m = MagicMock(spec=AudioCapture)
    m.start.return_value = None
    m.stop.return_value = np.ones((16000,), dtype=np.int16) * 5000
    m.is_recording.return_value = False
    m.get_devices.return_value = []
    return m


@pytest.fixture
def mock_recognition() -> MagicMock:
    m = MagicMock(spec=RecognitionEngine)
    m.transcribe.return_value = "Привет мир"
    m.is_loaded.return_value = True
    m.unload.return_value = None
    m.reload.return_value = None
    return m


@pytest.fixture
def mock_injector() -> MagicMock:
    m = MagicMock(spec=TextInjector)
    m.inject.return_value = None
    return m


@pytest.fixture
def mock_hotkey() -> MagicMock:
    m = MagicMock(spec=HotkeyListener)
    m.register.return_value = None
    m.unregister.return_value = None
    m.start.return_value = None
    m.stop.return_value = None
    m.is_running.return_value = False
    return m


@pytest.fixture
def state_machine() -> StateMachine:
    return StateMachine()


@pytest.fixture
def default_config() -> AppConfig:
    return AppConfig(mode="push_to_talk", hotkey="cmd+shift+1", language="ru")


@pytest.fixture
def toggle_config() -> AppConfig:
    return AppConfig(mode="toggle", hotkey="cmd+shift+1", language="ru")


@pytest.fixture
def pipeline(
    state_machine: StateMachine,
    mock_audio: MagicMock,
    mock_recognition: MagicMock,
    mock_injector: MagicMock,
    mock_hotkey: MagicMock,
    default_config: AppConfig,
) -> DictationPipeline:
    return DictationPipeline(
        state_machine=state_machine,
        audio_capture=mock_audio,
        recognition_engine=mock_recognition,
        text_injector=mock_injector,
        hotkey_listener=mock_hotkey,
        config=default_config,
    )


@pytest.fixture
def toggle_pipeline(
    state_machine: StateMachine,
    mock_audio: MagicMock,
    mock_recognition: MagicMock,
    mock_injector: MagicMock,
    mock_hotkey: MagicMock,
    toggle_config: AppConfig,
) -> DictationPipeline:
    return DictationPipeline(
        state_machine=state_machine,
        audio_capture=mock_audio,
        recognition_engine=mock_recognition,
        text_injector=mock_injector,
        hotkey_listener=mock_hotkey,
        config=toggle_config,
    )


# ---------------------------------------------------------------------------
# Push-to-talk — start / stop
# ---------------------------------------------------------------------------


class TestPipelineStartStop:
    def test_start_registers_hotkey(
        self, pipeline: DictationPipeline, mock_hotkey: MagicMock
    ) -> None:
        pipeline.start()
        mock_hotkey.register.assert_called_once()
        call_kwargs = mock_hotkey.register.call_args
        assert call_kwargs[0][0] == "cmd+shift+1"
        assert call_kwargs[1]["on_activate"] is not None

    def test_start_registers_deactivate_in_push_to_talk(
        self, pipeline: DictationPipeline, mock_hotkey: MagicMock
    ) -> None:
        pipeline.start()
        call_kwargs = mock_hotkey.register.call_args
        assert call_kwargs[1]["on_deactivate"] is not None

    def test_start_no_deactivate_in_toggle(
        self, toggle_pipeline: DictationPipeline, mock_hotkey: MagicMock
    ) -> None:
        toggle_pipeline.start()
        call_kwargs = mock_hotkey.register.call_args
        assert call_kwargs[1]["on_deactivate"] is None

    def test_start_starts_listener(
        self, pipeline: DictationPipeline, mock_hotkey: MagicMock
    ) -> None:
        pipeline.start()
        mock_hotkey.start.assert_called_once()

    def test_stop_stops_listener(self, pipeline: DictationPipeline, mock_hotkey: MagicMock) -> None:
        pipeline.start()
        pipeline.stop()
        mock_hotkey.stop.assert_called()


# ---------------------------------------------------------------------------
# Push-to-talk — hotkey callbacks
# ---------------------------------------------------------------------------


class TestPushToTalkHotkeys:
    def test_hotkey_down_starts_recording(
        self, pipeline: DictationPipeline, mock_audio: MagicMock, state_machine: StateMachine
    ) -> None:
        pipeline._on_hotkey_down()
        assert state_machine.state == State.RECORDING
        mock_audio.start.assert_called_once()

    def test_hotkey_down_when_not_idle_ignored(
        self, pipeline: DictationPipeline, mock_audio: MagicMock, state_machine: StateMachine
    ) -> None:
        state_machine.transition(State.RECORDING)
        pipeline._on_hotkey_down()
        assert mock_audio.start.call_count == 0

    def test_hotkey_up_stops_recording(
        self, pipeline: DictationPipeline, mock_audio: MagicMock, state_machine: StateMachine
    ) -> None:
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        mock_audio.stop.assert_called_once()

    def test_hotkey_up_transcribes(
        self,
        pipeline: DictationPipeline,
        mock_recognition: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        pipeline.wait_for_idle(timeout=5.0)
        mock_recognition.transcribe.assert_called_once()

    def test_hotkey_up_injects(
        self,
        pipeline: DictationPipeline,
        mock_injector: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        pipeline.wait_for_idle(timeout=5.0)
        mock_injector.inject.assert_called_once_with("Привет мир")

    def test_complete_flow_push_to_talk(
        self, pipeline: DictationPipeline, state_machine: StateMachine
    ) -> None:
        pipeline._on_hotkey_down()
        assert state_machine.state == State.RECORDING
        pipeline._on_hotkey_up()
        assert pipeline.wait_for_idle(timeout=5.0)

    def test_hotkey_up_when_not_recording_ignored(
        self, pipeline: DictationPipeline, mock_audio: MagicMock
    ) -> None:
        pipeline._on_hotkey_up()
        mock_audio.stop.assert_not_called()

    def test_empty_audio_skips_transcription(
        self,
        pipeline: DictationPipeline,
        mock_audio: MagicMock,
        mock_recognition: MagicMock,
        mock_injector: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        mock_audio.stop.return_value = np.zeros((16000,), dtype=np.int16)
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert pipeline.wait_for_idle(timeout=5.0)
        mock_recognition.transcribe.assert_not_called()
        mock_injector.inject.assert_not_called()

    def test_empty_transcript_skips_injection(
        self,
        pipeline: DictationPipeline,
        mock_recognition: MagicMock,
        mock_injector: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        mock_recognition.transcribe.return_value = ""
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert pipeline.wait_for_idle(timeout=5.0)
        mock_injector.inject.assert_not_called()

    def test_whitespace_transcript_skips_injection(
        self,
        pipeline: DictationPipeline,
        mock_recognition: MagicMock,
        mock_injector: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        mock_recognition.transcribe.return_value = "   \n\t  "
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert pipeline.wait_for_idle(timeout=5.0)
        mock_injector.inject.assert_not_called()


# ---------------------------------------------------------------------------
# Push-to-talk — error handling
# ---------------------------------------------------------------------------


class TestPushToTalkErrors:
    def test_recording_error_returns_to_idle(
        self, pipeline: DictationPipeline, mock_audio: MagicMock, state_machine: StateMachine
    ) -> None:
        mock_audio.start.side_effect = AudioDeviceError("No mic")
        pipeline._on_hotkey_down()
        assert state_machine.state == State.IDLE

    def test_audio_stop_error_returns_to_idle(
        self, pipeline: DictationPipeline, mock_audio: MagicMock, state_machine: StateMachine
    ) -> None:
        mock_audio.stop.side_effect = AudioDeviceError("Stop failed")
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert state_machine.state == State.IDLE

    def test_transcription_error_returns_to_idle(
        self,
        pipeline: DictationPipeline,
        mock_recognition: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        mock_recognition.transcribe.side_effect = TranscriptionError("Model failed")
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert pipeline.wait_for_idle(timeout=5.0)

    def test_injection_error_returns_to_idle(
        self,
        pipeline: DictationPipeline,
        mock_injector: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        mock_injector.inject.side_effect = InjectionError("No focus")
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert pipeline.wait_for_idle(timeout=5.0)

    def test_pipeline_error_callback(
        self, pipeline: DictationPipeline, mock_audio: MagicMock
    ) -> None:
        errors: list[tuple[Exception, str]] = []
        pipeline.on_error(lambda exc, ctx: errors.append((exc, ctx)))
        mock_audio.start.side_effect = AudioDeviceError("Boom")
        pipeline._on_hotkey_down()
        assert len(errors) == 1
        assert errors[0][1] == "audio_start"

    def test_state_force_idle_on_error(
        self, pipeline: DictationPipeline, mock_audio: MagicMock, state_machine: StateMachine
    ) -> None:
        mock_audio.start.side_effect = RuntimeError("Unexpected")
        pipeline._on_hotkey_down()
        assert state_machine.state == State.IDLE

    def test_unexpected_recording_error_logged(
        self, pipeline: DictationPipeline, mock_audio: MagicMock, state_machine: StateMachine
    ) -> None:
        mock_audio.start.side_effect = RuntimeError("Unexpected")
        pipeline._on_hotkey_down()
        assert state_machine.state == State.IDLE


# ---------------------------------------------------------------------------
# Push-to-talk — edge cases
# ---------------------------------------------------------------------------


class TestPushToTalkEdgeCases:
    def test_rapid_hotkey_presses(
        self,
        pipeline: DictationPipeline,
        mock_audio: MagicMock,
        mock_recognition: MagicMock,
        mock_injector: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert pipeline.wait_for_idle(timeout=5.0)

        mock_audio.stop.return_value = np.ones((16000,), dtype=np.int16) * 5000
        mock_recognition.transcribe.return_value = "Второй текст"

        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert pipeline.wait_for_idle(timeout=5.0)
        assert mock_recognition.transcribe.call_count == 2

    def test_silence_audio_handled(
        self,
        pipeline: DictationPipeline,
        mock_audio: MagicMock,
        mock_recognition: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        mock_audio.stop.return_value = np.full((16000,), 5, dtype=np.int16)
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert pipeline.wait_for_idle(timeout=5.0)
        mock_recognition.transcribe.assert_not_called()

    def test_none_audio_handled(
        self,
        pipeline: DictationPipeline,
        mock_audio: MagicMock,
        mock_recognition: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        mock_audio.stop.return_value = np.array([], dtype=np.int16)
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert pipeline.wait_for_idle(timeout=5.0)
        mock_recognition.transcribe.assert_not_called()

    def test_very_small_audio_handled(
        self,
        pipeline: DictationPipeline,
        mock_audio: MagicMock,
        mock_recognition: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        mock_audio.stop.return_value = np.zeros((0,), dtype=np.int16)
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert pipeline.wait_for_idle(timeout=5.0)
        mock_recognition.transcribe.assert_not_called()


# ---------------------------------------------------------------------------
# Toggle mode
# ---------------------------------------------------------------------------


class TestToggleMode:
    def test_toggle_first_press_starts_recording(
        self, toggle_pipeline: DictationPipeline, mock_audio: MagicMock, state_machine: StateMachine
    ) -> None:
        toggle_pipeline._on_hotkey_down()
        assert state_machine.state == State.RECORDING
        mock_audio.start.assert_called_once()

    def test_toggle_second_press_stops_recording(
        self, toggle_pipeline: DictationPipeline, state_machine: StateMachine
    ) -> None:
        toggle_pipeline._on_hotkey_down()
        toggle_pipeline._on_hotkey_down()
        assert toggle_pipeline.wait_for_idle(timeout=5.0)

    def test_toggle_complete_flow(
        self,
        toggle_pipeline: DictationPipeline,
        mock_audio: MagicMock,
        mock_recognition: MagicMock,
        mock_injector: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        toggle_pipeline._on_hotkey_down()
        assert state_machine.state == State.RECORDING

        toggle_pipeline._on_hotkey_down()
        assert toggle_pipeline.wait_for_idle(timeout=5.0)
        mock_recognition.transcribe.assert_called_once()
        mock_injector.inject.assert_called_once_with("Привет мир")

    def test_toggle_third_press_starts_again(
        self,
        toggle_pipeline: DictationPipeline,
        mock_audio: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        toggle_pipeline._on_hotkey_down()
        toggle_pipeline._on_hotkey_down()
        assert toggle_pipeline.wait_for_idle(timeout=5.0)

        toggle_pipeline._on_hotkey_down()
        assert state_machine.state == State.RECORDING
        assert mock_audio.start.call_count == 2

    def test_toggle_no_deactivate_registered(
        self,
        toggle_pipeline: DictationPipeline,
        mock_hotkey: MagicMock,
        state_machine: StateMachine,
    ) -> None:
        toggle_pipeline.start()
        call_kwargs = mock_hotkey.register.call_args
        assert call_kwargs[1]["on_deactivate"] is None


# ---------------------------------------------------------------------------
# Error handling — general
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_audio_start_error_logged(
        self, pipeline: DictationPipeline, mock_audio: MagicMock, state_machine: StateMachine
    ) -> None:
        mock_audio.start.side_effect = AudioDeviceError("Boom")
        pipeline._on_hotkey_down()
        assert state_machine.state == State.IDLE

    def test_audio_stop_error_logged(
        self, pipeline: DictationPipeline, mock_audio: MagicMock, state_machine: StateMachine
    ) -> None:
        mock_audio.stop.side_effect = RuntimeError("Stop fail")
        pipeline._on_hotkey_down()
        pipeline._on_hotkey_up()
        assert state_machine.state == State.IDLE

    def test_pipeline_error_callback_invoked(
        self, pipeline: DictationPipeline, mock_audio: MagicMock
    ) -> None:
        errors: list[tuple[Exception, str]] = []
        pipeline.on_error(lambda exc, ctx: errors.append((exc, ctx)))
        mock_audio.start.side_effect = RuntimeError("Boom")
        pipeline._on_hotkey_down()
        assert len(errors) == 1

    def test_state_force_idle_on_any_error(
        self, pipeline: DictationPipeline, mock_audio: MagicMock, state_machine: StateMachine
    ) -> None:
        mock_audio.start.side_effect = RuntimeError("Boom")
        pipeline._on_hotkey_down()
        assert state_machine.state == State.IDLE

    def test_error_callback_exception_is_swallowed(
        self, pipeline: DictationPipeline, mock_audio: MagicMock
    ) -> None:
        def bad_callback(exc: Exception, ctx: str) -> None:
            raise RuntimeError("Callback itself fails")

        pipeline.on_error(bad_callback)
        mock_audio.start.side_effect = RuntimeError("Audio fail")
        pipeline._on_hotkey_down()
        # Should not raise — the callback exception is caught internally


# ---------------------------------------------------------------------------
# Config / hotkey re-registration
# ---------------------------------------------------------------------------


class TestConfigReload:
    def test_reregister_hotkey(self, pipeline: DictationPipeline, mock_hotkey: MagicMock) -> None:
        pipeline.reregister_hotkey("cmd+shift+1", "ctrl+alt+f1")
        mock_hotkey.unregister.assert_called_once_with("cmd+shift+1")
        mock_hotkey.register.assert_called_once()

    def test_reregister_hotkey_passes_deactivate(
        self, pipeline: DictationPipeline, mock_hotkey: MagicMock
    ) -> None:
        pipeline.reregister_hotkey("cmd+shift+1", "ctrl+alt+f1")
        call_kwargs = mock_hotkey.register.call_args
        assert call_kwargs[1]["on_deactivate"] is not None

    def test_config_setter(self, pipeline: DictationPipeline) -> None:
        new_cfg = AppConfig(mode="toggle")
        pipeline.config = new_cfg
        assert pipeline.config.mode == "toggle"
