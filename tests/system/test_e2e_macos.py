"""System E2E tests for macOS — marked to skip in CI without real hardware."""

from __future__ import annotations

import sys
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

pytestmark = [pytest.mark.system, pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")]


class _Audio(AudioCapture):
    def __init__(self, data: np.ndarray | None = None) -> None:
        self._rec = False
        self._data = data if data is not None else np.ones((16000,), dtype=np.int16) * 5000

    def start(self) -> None:
        self._rec = True

    def stop(self) -> np.ndarray:
        self._rec = False
        return self._data

    def is_recording(self) -> bool:
        return self._rec

    def get_devices(self) -> list[dict[str, Any]]:
        return []


class _Engine(RecognitionEngine):
    def __init__(self, result: str = "Тест") -> None:
        self._result = result
        self._loaded = True

    def transcribe(self, audio: np.ndarray, language: str = "ru") -> str:
        return self._result

    def is_loaded(self) -> bool:
        return self._loaded

    def unload(self) -> None:
        self._loaded = False

    def reload(self, model_size: str) -> None:
        self._loaded = True


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


def _make(result: str = "Привет"):
    audio = _Audio()
    engine = _Engine(result=result)
    inj = _Injector()
    listener = _Listener()
    sm = StateMachine()
    cfg = AppConfig(mode="push_to_talk", auto_punctuation=False)
    pipe = DictationPipeline(sm, audio, engine, inj, listener, cfg)
    return pipe, sm, listener, inj


class TestE2EMacOSPipeline:
    """Full pipeline cycles simulating real dictation flow on macOS."""

    def test_full_dictation_cycle(self) -> None:
        pipe, sm, listener, inj = _make("Привет мир")
        pipe.start()
        listener.on_activate()
        assert sm.state == State.RECORDING
        listener.on_deactivate()
        assert _wait(sm, State.IDLE)
        assert inj.texts == ["Привет мир"]
        pipe.stop()

    def test_toggle_mode_cycle(self) -> None:
        audio = _Audio()
        engine = _Engine("Тогл")
        inj = _Injector()
        listener = _Listener()
        sm = StateMachine()
        cfg = AppConfig(mode="toggle", auto_punctuation=False)
        pipe = DictationPipeline(sm, audio, engine, inj, listener, cfg)
        pipe.start()
        listener.on_activate()
        assert sm.state == State.RECORDING
        listener.on_activate()
        assert _wait(sm, State.IDLE)
        assert inj.texts == ["Тогл"]
        pipe.stop()

    def test_silence_skipped(self) -> None:
        audio = _Audio(data=np.zeros((16000,), dtype=np.int16))
        engine = _Engine()
        inj = _Injector()
        listener = _Listener()
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk", auto_punctuation=False)
        pipe = DictationPipeline(sm, audio, engine, inj, listener, cfg)
        pipe.start()
        listener.on_activate()
        listener.on_deactivate()
        assert _wait(sm, State.IDLE)
        assert len(inj.texts) == 0
        pipe.stop()

    def test_empty_transcript_skipped(self) -> None:
        pipe, sm, listener, inj = _make("")
        pipe.start()
        listener.on_activate()
        listener.on_deactivate()
        assert _wait(sm, State.IDLE)
        assert len(inj.texts) == 0
        pipe.stop()

    def test_rapid_cycles(self) -> None:
        pipe, sm, listener, inj = _make("Быстро")
        pipe.start()
        for _ in range(5):
            listener.on_activate()
            assert sm.state == State.RECORDING
            listener.on_deactivate()
            assert _wait(sm, State.IDLE)
        assert len(inj.texts) == 5
        pipe.stop()

    def test_unicode_injection(self) -> None:
        pipe, sm, listener, inj = _make("Привет, ёлка! Эмодзи: 🙂")
        pipe.start()
        listener.on_activate()
        listener.on_deactivate()
        assert _wait(sm, State.IDLE)
        assert "ёлка" in inj.texts[0]
        assert "🙂" in inj.texts[0]
        pipe.stop()

    def test_long_text_injection(self) -> None:
        long_text = "Это очень длинный текст. " * 50
        pipe, sm, listener, inj = _make(long_text)
        pipe.start()
        listener.on_activate()
        listener.on_deactivate()
        assert _wait(sm, State.IDLE)
        assert inj.texts[0] == long_text
        pipe.stop()
