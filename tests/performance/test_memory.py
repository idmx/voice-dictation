"""Memory usage tests to detect leaks."""

from __future__ import annotations

import gc
import time
import tracemalloc
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
        time.sleep(0.005)
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
    config = AppConfig(mode="push_to_talk", hotkey="cmd+shift+1", language="ru")
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


def _run_cycle(
    pipeline: DictationPipeline,
    sm: StateMachine,
    listener: MockHotkeyListener,
) -> None:
    listener.simulate_press()
    assert _wait_for_state(sm, State.RECORDING, timeout=5.0)
    listener.simulate_release()
    assert _wait_for_state(sm, State.IDLE, timeout=5.0)


@pytest.mark.performance
@pytest.mark.timeout(30)
class TestMemoryUsage:
    def test_idle_baseline(self) -> None:
        pipeline, sm, listener, _, _, _ = _make_pipeline()
        pipeline.start()

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()
        time.sleep(0.3)
        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in stats)
        assert total_diff < 5 * 1024 * 1024, f"Idle memory drift: {total_diff} bytes"
        pipeline.stop()

    def test_after_10_cycles(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="Память")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )
        pipeline.start()

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        for _ in range(10):
            _run_cycle(pipeline, sm, listener)

        time.sleep(0.3)
        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in stats)
        growth_mb = total_diff / (1024 * 1024)
        assert growth_mb < 10, f"Memory growth after 10 cycles: {growth_mb:.2f}MB"
        assert engine.transcribe_called == 10
        assert len(injector.injected_texts) == 10
        pipeline.stop()

    def test_model_loading_memory(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="Модель")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )
        pipeline.start()

        gc.collect()
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        for _ in range(20):
            _run_cycle(pipeline, sm, listener)

        time.sleep(0.3)
        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in stats)
        growth_mb = total_diff / (1024 * 1024)
        assert growth_mb < 10, f"Memory growth after 20 transcribe calls: {growth_mb:.2f}MB"
        assert engine.transcribe_called == 20
        pipeline.stop()
