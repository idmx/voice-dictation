"""Performance benchmarks for pipeline latency."""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np
import pytest

from voice_dictation.audio.base import AudioCapture
from voice_dictation.config.schema import AppConfig
from voice_dictation.core.state import State, StateMachine
from voice_dictation.hotkey.base import HotkeyListener
from voice_dictation.injection.base import TextInjector
from voice_dictation.pipeline import DictationPipeline
from voice_dictation.recognition.base import RecognitionEngine


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
        self._call_event = threading.Event()
        self._transcribe_event = threading.Event()

    def transcribe(self, audio: np.ndarray, language: str = "ru") -> str:
        self.transcribe_called += 1
        self._call_event.set()
        self._transcribe_event.set()
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
        self._inject_event = threading.Event()
        self._inject_count = 0

    def inject(self, text: str) -> None:
        self._inject_count += 1
        self._inject_event.set()
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
        self.on_deactivate: Any | None = None

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


PipelineParts = tuple[
    "DictationPipeline",
    "StateMachine",
    "MockHotkeyListener",
    "MockAudioCapture",
    "MockRecognitionEngine",
    "MockTextInjector",
]


def _wait_for_state(sm: StateMachine, state: State, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while sm.state != state and time.monotonic() < end:
        time.sleep(0.001)
    return sm.state == state


def _make_pipeline(
    audio: MockAudioCapture | None = None,
    engine: MockRecognitionEngine | None = None,
    injector: MockTextInjector | None = None,
) -> PipelineParts:
    if audio is None:
        audio = MockAudioCapture()
    if engine is None:
        engine = MockRecognitionEngine()
    if injector is None:
        injector = MockTextInjector()
    config = AppConfig(mode="push_to_talk", hotkey="cmd+shift+1", language="ru", auto_punctuation=False)
    listener = MockHotkeyListener(mode="push_to_talk")
    sm = StateMachine()
    pipeline = DictationPipeline(
        state_machine=sm,
        audio_capture=audio,
        recognition_engine=engine,
        text_injector=injector,
        hotkey_listener=listener,
        config=config,
    )
    return pipeline, sm, listener, audio, engine, injector


@pytest.mark.performance
@pytest.mark.timeout(15)
class TestLatencyBenchmarks:
    def test_hotkey_to_recording_start(self) -> None:
        pipeline, sm, listener, _, _, _ = _make_pipeline()
        pipeline.start()

        start = time.monotonic()
        listener.simulate_press()
        assert _wait_for_state(sm, State.RECORDING, timeout=5.0)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 100, f"Hotkey to recording start took {elapsed_ms:.2f}ms"
        pipeline.stop()

    def test_recording_stop_to_transcribe_start(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine()
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )
        pipeline.start()

        listener.simulate_press()
        assert _wait_for_state(sm, State.RECORDING, timeout=5.0)
        engine._call_event.clear()

        start = time.monotonic()
        listener.simulate_release()

        assert engine._call_event.wait(timeout=5.0), "transcribe() was not called"
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 100, f"Recording stop to transcribe took {elapsed_ms:.2f}ms"
        pipeline.stop()

    def test_inject_text_latency(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="Тестовый текст")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )
        pipeline.start()

        listener.simulate_press()
        assert _wait_for_state(sm, State.RECORDING, timeout=5.0)

        injector._inject_event.clear()

        start = time.monotonic()
        listener.simulate_release()

        assert injector._inject_event.wait(timeout=5.0), "inject() was not called"
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 100, f"Transcript ready to inject took {elapsed_ms:.2f}ms"
        pipeline.stop()

    def test_full_pipeline_2sec_dictation(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="Полный цикл")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )
        pipeline.start()

        start = time.monotonic()
        listener.simulate_press()
        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 500, f"Full pipeline took {elapsed_ms:.2f}ms"
        assert injector.injected_texts == ["Полный цикл"]
        pipeline.stop()

    def test_10_consecutive_cycles(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="Цикл")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )
        pipeline.start()

        start = time.monotonic()
        for i in range(10):
            listener.simulate_press()
            assert _wait_for_state(sm, State.RECORDING, timeout=5.0)
            listener.simulate_release()
            assert _wait_for_state(sm, State.IDLE, timeout=5.0), f"Cycle {i} did not complete"
        elapsed_s = time.monotonic() - start

        assert elapsed_s < 5.0, f"10 cycles took {elapsed_s:.2f}s"
        assert engine.transcribe_called == 10
        assert len(injector.injected_texts) == 10
        pipeline.stop()
