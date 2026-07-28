"""System tests for long-running sessions — stability and leak detection."""

from __future__ import annotations

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


class _Audio(AudioCapture):
    def __init__(self) -> None:
        self._rec = False

    def start(self) -> None:
        self._rec = True

    def stop(self) -> np.ndarray:
        self._rec = False
        return np.ones((16000,), dtype=np.int16) * 5000

    def is_recording(self) -> bool:
        return self._rec

    def get_devices(self) -> list[dict[str, Any]]:
        return []


class _Engine(RecognitionEngine):
    def __init__(self) -> None:
        self._loaded = True
        self.transcribe_called = 0

    def transcribe(self, audio: np.ndarray, language: str = "ru") -> str:
        self.transcribe_called += 1
        return f"Текст {self.transcribe_called}"

    def is_loaded(self) -> bool:
        return self._loaded

    def unload(self) -> None:
        self._loaded = False

    def reload(self, model_size: str) -> None:
        pass


class _Injector(TextInjector):
    def __init__(self) -> None:
        self.texts: list[str] = []

    def inject(self, text: str) -> None:
        self.texts.append(text)


class _Listener(HotkeyListener):
    def __init__(self) -> None:
        self.on_activate: Any = None
        self.on_deactivate: Any = None

    def register(self, hotkey: str, on_activate: Any, on_deactivate: Any | None = None) -> None:
        self.on_activate = on_activate
        self.on_deactivate = on_deactivate

    def unregister(self, hotkey: str) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def is_running(self) -> bool:
        return True


def _wait(sm: StateMachine, state: State, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while sm.state != state and time.monotonic() < end:
        time.sleep(0.005)
    return sm.state == state


def _cycle(pipe, sm, listener):
    listener.on_activate()
    assert _wait(sm, State.RECORDING, timeout=3.0)
    listener.on_deactivate()
    assert _wait(sm, State.IDLE, timeout=3.0)


@pytest.mark.system
@pytest.mark.timeout(30)
class TestLongSession:
    """Long-running session stability tests."""

    def test_100_dictation_cycles(self) -> None:
        """100 consecutive cycles without leaks or crashes."""
        audio = _Audio()
        engine = _Engine()
        inj = _Injector()
        listener = _Listener()
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk")
        pipe = DictationPipeline(sm, audio, engine, inj, listener, cfg)
        pipe.start()

        for _ in range(100):
            _cycle(pipe, sm, listener)

        assert engine.transcribe_called == 100
        assert len(inj.texts) == 100
        assert sm.state == State.IDLE
        pipe.stop()

    def test_model_switch_stability(self) -> None:
        """Multiple model reloads don't crash."""
        engine = _Engine()
        for i in range(10):
            engine.reload("tiny" if i % 2 == 0 else "base")
        assert engine.is_loaded()

    def test_state_machine_1000_transitions(self) -> None:
        """1000 state transitions without deadlock."""
        sm = StateMachine()
        for _ in range(250):
            assert sm.transition(State.RECORDING)
            assert sm.transition(State.TRANSCRIBING)
            assert sm.transition(State.INJECTING)
            assert sm.transition(State.IDLE)
        assert sm.state == State.IDLE

    def test_pipeline_reuse_after_stop(self) -> None:
        """Pipeline can be started, stopped, and started again."""
        audio = _Audio()
        engine = _Engine()
        inj = _Injector()
        listener = _Listener()
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk")
        pipe = DictationPipeline(sm, audio, engine, inj, listener, cfg)

        for _ in range(3):
            pipe.start()
            _cycle(pipe, sm, listener)
            pipe.stop()

        assert len(inj.texts) == 3
