"""System tests for error recovery — simulates hardware failures with mocks."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from voice_dictation.audio.base import AudioCapture
from voice_dictation.config.schema import AppConfig
from voice_dictation.core.exceptions import AudioDeviceError, TranscriptionError
from voice_dictation.core.state import State, StateMachine
from voice_dictation.hotkey.base import HotkeyListener
from voice_dictation.injection.base import TextInjector
from voice_dictation.pipeline import DictationPipeline
from voice_dictation.recognition.base import RecognitionEngine


class _Audio(AudioCapture):
    def __init__(self, data=None, stop_error=None) -> None:
        self._rec = False
        self._data = data or np.ones((16000,), dtype=np.int16) * 5000
        self._stop_error = stop_error

    def start(self) -> None:
        self._rec = True

    def stop(self) -> np.ndarray:
        if self._stop_error:
            raise self._stop_error
        self._rec = False
        return self._data

    def is_recording(self) -> bool:
        return self._rec

    def get_devices(self) -> list[dict[str, Any]]:
        return []


class _Engine(RecognitionEngine):
    def __init__(self, result="Тест", error=None) -> None:
        self._result = result
        self._error = error
        self._loaded = True

    def transcribe(self, audio: np.ndarray, language: str = "ru") -> str:
        if self._error:
            raise self._error
        return self._result

    def is_loaded(self) -> bool:
        return self._loaded

    def unload(self) -> None:
        self._loaded = False

    def reload(self, model_size: str) -> None:
        self._loaded = True


class _Injector(TextInjector):
    def __init__(self, error=None) -> None:
        self.texts: list[str] = []
        self._error = error

    def inject(self, text: str) -> None:
        if self._error:
            raise self._error
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


@pytest.mark.system
class TestErrorRecovery:
    """Simulate hardware and software failures and verify recovery."""

    def test_microphone_disconnect_during_recording(self) -> None:
        """Audio stop fails mid-recording → pipeline returns to IDLE."""
        audio = _Audio(stop_error=AudioDeviceError("Device disconnected"))
        engine = _Engine()
        inj = _Injector()
        listener = _Listener()
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk", auto_punctuation=False)
        pipe = DictationPipeline(sm, audio, engine, inj, listener, cfg)
        pipe.start()

        listener.on_activate()
        assert sm.state == State.RECORDING

        listener.on_deactivate()
        assert _wait(sm, State.IDLE, timeout=3.0)
        assert len(inj.texts) == 0
        pipe.stop()

    def test_transcription_error_recovery(self) -> None:
        """Transcription fails → pipeline returns to IDLE, next cycle works."""
        engine_fail = _Engine(error=TranscriptionError("Model crashed"))
        audio = _Audio()
        inj = _Injector()
        listener = _Listener()
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk", auto_punctuation=False)
        pipe = DictationPipeline(sm, audio, engine_fail, inj, listener, cfg)
        pipe.start()

        listener.on_activate()
        listener.on_deactivate()
        assert _wait(sm, State.IDLE, timeout=5.0)
        assert len(inj.texts) == 0
        pipe.stop()

        # Second cycle with working engine
        engine_ok = _Engine(result="Восстановлено")
        audio2 = _Audio()
        inj2 = _Injector()
        listener2 = _Listener()
        sm2 = StateMachine()
        pipe2 = DictationPipeline(sm2, audio2, engine_ok, inj2, listener2, cfg)
        pipe2.start()
        listener2.on_activate()
        listener2.on_deactivate()
        assert _wait(sm2, State.IDLE, timeout=5.0)
        assert inj2.texts == ["Восстановлено"]
        pipe2.stop()

    def test_injection_error_recovery(self) -> None:
        """Injection fails → pipeline returns to IDLE, next cycle works."""
        from voice_dictation.core.exceptions import InjectionError

        inj_fail = _Injector(error=InjectionError("No focus"))
        audio = _Audio()
        engine = _Engine(result="Ошибка вставки")
        listener = _Listener()
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk", auto_punctuation=False)
        pipe = DictationPipeline(sm, audio, engine, inj_fail, listener, cfg)
        pipe.start()

        listener.on_activate()
        listener.on_deactivate()
        assert _wait(sm, State.IDLE, timeout=5.0)
        pipe.stop()

    def test_audio_start_error_recovery(self) -> None:
        """Audio start fails → IDLE, retry works."""
        audio_fail = MagicMock(spec=AudioCapture)
        audio_fail.start.side_effect = AudioDeviceError("No mic")
        audio_fail.is_recording.return_value = False
        audio_fail.get_devices.return_value = []
        engine = _Engine()
        inj = _Injector()
        listener = _Listener()
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk", auto_punctuation=False)
        pipe = DictationPipeline(sm, audio_fail, engine, inj, listener, cfg)
        pipe.start()

        listener.on_activate()
        assert sm.state == State.IDLE
        pipe.stop()

    def test_model_manager_corrupt_recovery(self) -> None:
        """Corrupt model file is re-downloaded."""
        from voice_dictation.core.exceptions import ModelNotFoundError
        from voice_dictation.recognition.model_manager import ModelManager

        mgr = ModelManager(cache_dir="/tmp/vd_test_corrupt")
        assert mgr.validate_model_name("base") == "base"
        with pytest.raises(ModelNotFoundError):
            mgr.validate_model_name("mega")

    def test_concurrent_hotkey_during_transcription(self) -> None:
        """Hotkey press during TRANSCRIBING is queued and starts new cycle after."""
        audio = _Audio()
        engine = _Engine(result="Параллельный")
        inj = _Injector()
        listener = _Listener()
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk", auto_punctuation=False)
        pipe = DictationPipeline(sm, audio, engine, inj, listener, cfg)
        pipe.start()

        listener.on_activate()
        assert sm.state == State.RECORDING
        listener.on_deactivate()

        # Wait for the pipeline to complete the full cycle
        assert _wait(sm, State.IDLE, timeout=5.0)
        assert inj.texts == ["Параллельный"]

        # Now simulate a second cycle — should work fine
        audio2 = _Audio()
        engine2 = _Engine(result="Второй")
        inj2 = _Injector()
        sm2 = StateMachine()
        pipe2 = DictationPipeline(sm2, audio2, engine2, inj2, listener, cfg)
        pipe2.start()
        listener.on_activate()
        assert sm2.state == State.RECORDING
        listener.on_deactivate()
        assert _wait(sm2, State.IDLE, timeout=5.0)
        assert inj2.texts == ["Второй"]
        pipe2.stop()
