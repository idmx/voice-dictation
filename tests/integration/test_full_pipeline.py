"""Integration tests for the full voice-dictation pipeline.

These tests exercise the :class:`DictationPipeline` orchestrator with mocked
external components (audio device, whisper model, keyboard hooks, text
injection) so that the real orchestration logic is verified without requiring
real hardware. The :class:`StateMachine` is real — everything else is mocked
concretely.
"""

from __future__ import annotations

import threading
import time
from typing import Any

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
# Concrete mock components (implement ABCs for realism)
# ---------------------------------------------------------------------------


class MockAudioCapture(AudioCapture):
    def __init__(
        self,
        audio_data: np.ndarray | None = None,
        start_side_effect: BaseException | None = None,
        stop_side_effect: BaseException | None = None,
    ) -> None:
        self._recording = False
        self.start_called = 0
        self.stop_called = 0
        self._audio_data = (
            audio_data if audio_data is not None else np.ones((16000,), dtype=np.int16) * 5000
        )
        self._start_side_effect = start_side_effect
        self._stop_side_effect = stop_side_effect

    def start(self) -> None:
        self.start_called += 1
        if self._start_side_effect is not None:
            raise self._start_side_effect
        self._recording = True

    def stop(self) -> np.ndarray:
        self.stop_called += 1
        if self._stop_side_effect is not None:
            raise self._stop_side_effect
        self._recording = False
        return self._audio_data

    def is_recording(self) -> bool:
        return self._recording

    def get_devices(self) -> list[dict[str, Any]]:
        return []


class MockRecognitionEngine(RecognitionEngine):
    def __init__(
        self,
        transcription_result: str = "Привет мир",
        transcribe_side_effect: BaseException | None = None,
    ) -> None:
        self._loaded = True
        self._transcription_result = transcription_result
        self._transcribe_side_effect = transcribe_side_effect
        self.transcribe_called = 0
        self.unload_called = 0
        self.reload_called = 0

    def transcribe(self, audio: np.ndarray, language: str = "ru") -> str:
        self.transcribe_called += 1
        if self._transcribe_side_effect is not None:
            raise self._transcribe_side_effect
        return self._transcription_result

    def is_loaded(self) -> bool:
        return self._loaded

    def unload(self) -> None:
        self.unload_called += 1
        self._loaded = False

    def reload(self, model_size: str) -> None:
        self.reload_called += 1
        self._loaded = True


class MockTextInjector(TextInjector):
    def __init__(self, inject_side_effect: BaseException | None = None) -> None:
        self.injected_texts: list[str] = []
        self._inject_side_effect = inject_side_effect

    def inject(self, text: str) -> None:
        if self._inject_side_effect is not None:
            raise self._inject_side_effect
        self.injected_texts.append(text)


class MockHotkeyListener(HotkeyListener):
    def __init__(self, mode: str = "push_to_talk") -> None:
        self._mode = mode
        self._running = False
        self._registered: list[dict[str, Any]] = []
        self._unregistered: list[str] = []
        self.on_activate: Any = None
        self.on_deactivate: Any = None

    def register(
        self,
        hotkey: str,
        on_activate: Any,
        on_deactivate: Any | None = None,
    ) -> None:
        self._registered.append(
            {
                "hotkey": hotkey,
                "on_activate": on_activate,
                "on_deactivate": on_deactivate,
            }
        )
        self.on_activate = on_activate
        self.on_deactivate = on_deactivate

    def unregister(self, hotkey: str) -> None:
        self._unregistered.append(hotkey)

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def simulate_press(self) -> None:
        if self.on_activate is not None:
            self.on_activate()

    def simulate_release(self) -> None:
        if self.on_deactivate is not None:
            self.on_deactivate()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StateTracker:
    def __init__(self) -> None:
        self.transitions: list[tuple[State, State]] = []
        self._lock = threading.RLock()

    def __call__(self, old: State, new: State) -> None:
        with self._lock:
            self.transitions.append((old, new))

    @property
    def states(self) -> list[State]:
        with self._lock:
            return [t[1] for t in self.transitions]

    def has_state(self, state: State) -> bool:
        with self._lock:
            return state in [t[1] for t in self.transitions]


def _wait_for_state(sm: StateMachine, state: State, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while sm.state != state and time.monotonic() < end:
        time.sleep(0.01)
    return sm.state == state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ptt_components():
    audio = MockAudioCapture()
    engine = MockRecognitionEngine(transcription_result="Привет мир")
    injector = MockTextInjector()
    listener = MockHotkeyListener(mode="push_to_talk")
    sm = StateMachine()
    tracker = _StateTracker()
    sm.on_transition(tracker)
    cfg = AppConfig(mode="push_to_talk", hotkey="cmd+shift+d", language="ru")
    pipeline = DictationPipeline(
        state_machine=sm,
        audio_capture=audio,
        recognition_engine=engine,
        text_injector=injector,
        hotkey_listener=listener,
        config=cfg,
    )
    return pipeline, sm, tracker, audio, engine, injector, listener


@pytest.fixture
def toggle_components():
    audio = MockAudioCapture()
    engine = MockRecognitionEngine(transcription_result="Привет мир")
    injector = MockTextInjector()
    listener = MockHotkeyListener(mode="toggle")
    sm = StateMachine()
    tracker = _StateTracker()
    sm.on_transition(tracker)
    cfg = AppConfig(mode="toggle", hotkey="cmd+shift+d", language="ru")
    pipeline = DictationPipeline(
        state_machine=sm,
        audio_capture=audio,
        recognition_engine=engine,
        text_injector=injector,
        hotkey_listener=listener,
        config=cfg,
    )
    return pipeline, sm, tracker, audio, engine, injector, listener


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestCompleteFlowPushToTalk:
    def test_complete_flow(self, ptt_components) -> None:
        pipeline, sm, tracker, audio, engine, injector, listener = ptt_components
        pipeline.start()

        listener.simulate_press()
        assert sm.state == State.RECORDING
        assert audio.start_called == 1

        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert audio.stop_called == 1
        assert engine.transcribe_called == 1
        assert injector.injected_texts == ["Привет мир"]
        pipeline.stop()


class TestCompleteFlowToggle:
    def test_complete_flow(self, toggle_components) -> None:
        pipeline, sm, tracker, audio, engine, injector, listener = toggle_components
        pipeline.start()

        listener.simulate_press()
        assert sm.state == State.RECORDING

        listener.simulate_press()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert audio.stop_called == 1
        assert engine.transcribe_called == 1
        assert injector.injected_texts == ["Привет мир"]
        pipeline.stop()


class TestPipelineWithSilence:
    def test_silence_no_injection(self) -> None:
        audio = MockAudioCapture(audio_data=np.zeros((16000,), dtype=np.int16))
        engine = MockRecognitionEngine()
        injector = MockTextInjector()
        listener = MockHotkeyListener(mode="push_to_talk")
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk")
        pipeline = DictationPipeline(
            state_machine=sm,
            audio_capture=audio,
            recognition_engine=engine,
            text_injector=injector,
            hotkey_listener=listener,
            config=cfg,
        )
        pipeline.start()

        listener.simulate_press()
        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert engine.transcribe_called == 0
        assert injector.injected_texts == []
        pipeline.stop()


class TestPipelineWithNoise:
    def test_noise_injection(self) -> None:
        audio_data = np.random.randint(-5000, 5000, (16000,), dtype=np.int16)
        audio = MockAudioCapture(audio_data=audio_data)
        engine = MockRecognitionEngine(transcription_result="Гарблед текст")
        injector = MockTextInjector()
        listener = MockHotkeyListener(mode="push_to_talk")
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk")
        pipeline = DictationPipeline(
            state_machine=sm,
            audio_capture=audio,
            recognition_engine=engine,
            text_injector=injector,
            hotkey_listener=listener,
            config=cfg,
        )
        pipeline.start()

        listener.simulate_press()
        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert engine.transcribe_called == 1
        assert injector.injected_texts == ["Гарблед текст"]
        pipeline.stop()


class TestPipelineRecordingError:
    def test_audio_start_error_returns_to_idle(self) -> None:
        audio = MockAudioCapture(start_side_effect=AudioDeviceError("No mic"))
        engine = MockRecognitionEngine()
        injector = MockTextInjector()
        listener = MockHotkeyListener(mode="push_to_talk")
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk")
        pipeline = DictationPipeline(
            state_machine=sm,
            audio_capture=audio,
            recognition_engine=engine,
            text_injector=injector,
            hotkey_listener=listener,
            config=cfg,
        )
        pipeline.start()

        listener.simulate_press()
        assert _wait_for_state(sm, State.IDLE, timeout=3.0)
        assert engine.transcribe_called == 0
        assert injector.injected_texts == []
        pipeline.stop()


class TestPipelineRecognitionError:
    def test_recognition_error_returns_to_idle(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcribe_side_effect=TranscriptionError("Model failed"))
        injector = MockTextInjector()
        listener = MockHotkeyListener(mode="push_to_talk")
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk")
        pipeline = DictationPipeline(
            state_machine=sm,
            audio_capture=audio,
            recognition_engine=engine,
            text_injector=injector,
            hotkey_listener=listener,
            config=cfg,
        )
        pipeline.start()

        listener.simulate_press()
        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert engine.transcribe_called == 1
        assert injector.injected_texts == []
        pipeline.stop()


class TestPipelineInjectionError:
    def test_injection_error_returns_to_idle(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="Ошибка")
        injector = MockTextInjector(inject_side_effect=InjectionError("No focus"))
        listener = MockHotkeyListener(mode="push_to_talk")
        sm = StateMachine()
        tracker = _StateTracker()
        sm.on_transition(tracker)
        cfg = AppConfig(mode="push_to_talk")
        pipeline = DictationPipeline(
            state_machine=sm,
            audio_capture=audio,
            recognition_engine=engine,
            text_injector=injector,
            hotkey_listener=listener,
            config=cfg,
        )
        pipeline.start()

        listener.simulate_press()
        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert engine.transcribe_called == 1
        assert tracker.has_state(State.INJECTING)
        pipeline.stop()


class TestRapidHotkeyPresses:
    def test_two_rapid_cycles(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="Быстрый тест")
        injector = MockTextInjector()
        listener = MockHotkeyListener(mode="push_to_talk")
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk")
        pipeline = DictationPipeline(
            state_machine=sm,
            audio_capture=audio,
            recognition_engine=engine,
            text_injector=injector,
            hotkey_listener=listener,
            config=cfg,
        )
        pipeline.start()

        listener.simulate_press()
        assert sm.state == State.RECORDING

        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert injector.injected_texts == ["Быстрый тест"]

        listener.simulate_press()
        assert sm.state == State.RECORDING

        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert len(injector.injected_texts) == 2
        pipeline.stop()


class TestCancelDuringRecording:
    def test_cancel_prevents_transcription(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine()
        injector = MockTextInjector()
        listener = MockHotkeyListener(mode="push_to_talk")
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk")
        pipeline = DictationPipeline(
            state_machine=sm,
            audio_capture=audio,
            recognition_engine=engine,
            text_injector=injector,
            hotkey_listener=listener,
            config=cfg,
        )
        pipeline.start()

        listener.simulate_press()
        assert sm.state == State.RECORDING

        sm.force_idle()
        assert sm.state == State.IDLE

        listener.simulate_release()
        time.sleep(0.3)
        assert engine.transcribe_called == 0
        assert injector.injected_texts == []
        pipeline.stop()
