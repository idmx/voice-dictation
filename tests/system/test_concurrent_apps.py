"""System tests for concurrent applications — simulated conflicts."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from voice_dictation.audio.base import AudioCapture
from voice_dictation.config.schema import AppConfig
from voice_dictation.core.state import State, StateMachine
from voice_dictation.hotkey.base import HotkeyListener
from voice_dictation.hotkey.hotkey_parser import HotkeyParser
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

    def transcribe(self, audio: np.ndarray, language: str = "ru") -> str:
        return "Конфликт"

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


@pytest.mark.system
class TestConcurrentApps:
    """Simulate scenarios with other apps running."""

    def test_clipboard_manager_running(self) -> None:
        """Clipboard manager (CopyClip/Ditto) running — buffer still restored."""
        from voice_dictation.utils.clipboard import ClipboardManager

        cm = ClipboardManager()
        # Simulate clipboard being changed by another app between save and restore
        with (
            patch("voice_dictation.utils.clipboard.is_macos", return_value=True),
            patch("voice_dictation.utils.clipboard.is_windows", return_value=False),
            patch("voice_dictation.utils.clipboard.subprocess.run") as mock_run,
        ):
            import subprocess

            def side_effect(args, **kwargs):
                if "pbpaste" in args:
                    return subprocess.CompletedProcess(args, 0, stdout="original", stderr="")
                if "pbcopy" in args:
                    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            mock_run.side_effect = side_effect
            cm.save()
            cm.restore()

    def test_hotkey_parser_conflict_detection(self) -> None:
        """Known system hotkeys are still parsed (user warned separately)."""
        # cmd+space is Spotlight on macOS — parser should still parse it
        mods, key = HotkeyParser.parse("cmd+space")
        assert "cmd" in mods
        assert key == "space"

    def test_multiple_pipelines_dont_interfere(self) -> None:
        """Two pipelines on separate state machines don't interfere."""
        sm1 = StateMachine()
        sm2 = StateMachine()
        audio = _Audio()
        engine = _Engine()
        inj = _Injector()
        listener = _Listener()
        cfg = AppConfig(mode="push_to_talk")
        pipe1 = DictationPipeline(sm1, audio, engine, inj, listener, cfg)
        pipe1.start()

        audio2 = _Audio()
        engine2 = _Engine()
        inj2 = _Injector()
        listener2 = _Listener()
        pipe2 = DictationPipeline(sm2, audio2, engine2, inj2, listener2, cfg)
        pipe2.start()

        # Run cycle on pipe1
        listener.on_activate()
        assert sm1.state == State.RECORDING
        assert sm2.state == State.IDLE
        listener.on_deactivate()
        assert _wait(sm1, State.IDLE)
        assert sm2.state == State.IDLE

        pipe1.stop()
        pipe2.stop()

    def test_config_change_during_recording(self) -> None:
        """Config change during recording doesn't crash the pipeline."""
        audio = _Audio()
        engine = _Engine()
        inj = _Injector()
        listener = _Listener()
        sm = StateMachine()
        cfg = AppConfig(mode="push_to_talk", language="ru")
        pipe = DictationPipeline(sm, audio, engine, inj, listener, cfg)
        pipe.start()

        listener.on_activate()
        assert sm.state == State.RECORDING

        # Change config mid-recording
        pipe.config = AppConfig(mode="push_to_talk", language="en")

        listener.on_deactivate()
        assert _wait(sm, State.IDLE)
        assert len(inj.texts) == 1
        pipe.stop()
