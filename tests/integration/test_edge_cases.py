"""Edge-case integration tests for robustness."""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np
import pytest

from voice_dictation.audio.base import AudioCapture
from voice_dictation.config.schema import AppConfig
from voice_dictation.core.exceptions import AudioDeviceError, InjectionError
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

    def transcribe(self, audio: np.ndarray, language: str = "ru") -> str:
        self.transcribe_called += 1
        self._call_event.set()
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


class CountingInjector(TextInjector):
    def __init__(self, fail_until: int = 1) -> None:
        self.injected_texts: list[str] = []
        self._inject_count = 0
        self._fail_until = fail_until

    def inject(self, text: str) -> None:
        self._inject_count += 1
        if self._inject_count <= self._fail_until:
            raise InjectionError(f"Injection failed (attempt {self._inject_count})")
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
    "TextInjector",
]


def _make_pipeline(
    audio: MockAudioCapture | None = None,
    engine: MockRecognitionEngine | None = None,
    injector: TextInjector | None = None,
    config: AppConfig | None = None,
    mode: str = "push_to_talk",
) -> PipelineParts:
    if audio is None:
        audio = MockAudioCapture()
    if engine is None:
        engine = MockRecognitionEngine()
    if injector is None:
        injector = MockTextInjector()
    if config is None:
        config = AppConfig(mode=mode, hotkey="cmd+shift+1", language="ru")
    listener = MockHotkeyListener(mode=mode)
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


def _wait_for_state(sm: StateMachine, state: State, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while sm.state != state and time.monotonic() < end:
        time.sleep(0.01)
    return sm.state == state


# ------------------------------------------------------------------
# Audio edge cases
# ------------------------------------------------------------------


@pytest.mark.timeout(10)
class TestMicrophoneDisconnectMidRecording:
    def test_microphone_disconnect_mid_recording(self) -> None:
        audio = MockAudioCapture(
            stop_side_effect=AudioDeviceError("Microphone disconnected")
        )
        engine = MockRecognitionEngine()
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        assert sm.state == State.RECORDING

        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)

        assert audio.stop_called == 1
        assert engine.transcribe_called == 0
        assert injector.injected_texts == []
        pipeline.stop()


@pytest.mark.timeout(10)
class TestNoAudioInput:
    def test_no_audio_input(self) -> None:
        audio = MockAudioCapture(audio_data=np.zeros((16000,), dtype=np.int16))
        engine = MockRecognitionEngine(transcription_result="")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        listener.simulate_release()

        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert engine.transcribe_called == 0
        assert injector.injected_texts == []
        pipeline.stop()


@pytest.mark.timeout(10)
class TestVeryLongRecording60s:
    def test_very_long_recording_60s(self) -> None:
        audio_data = np.random.randint(1000, 5000, (960000,), dtype=np.int16)
        audio = MockAudioCapture(audio_data=audio_data)
        engine = MockRecognitionEngine(transcription_result="Длинная запись обработана")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        listener.simulate_release()

        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert engine.transcribe_called == 1
        assert injector.injected_texts == ["Длинная запись обработана"]
        pipeline.stop()


@pytest.mark.timeout(10)
class TestAudioStartCalledTwiceRapidly:
    def test_audio_start_called_twice_rapidly(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine()
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        assert sm.state == State.RECORDING

        listener.simulate_press()
        time.sleep(0.1)

        assert audio.start_called == 1
        assert sm.state == State.RECORDING

        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        pipeline.stop()


# ------------------------------------------------------------------
# Recognition edge cases
# ------------------------------------------------------------------


@pytest.mark.timeout(10)
class TestEmptyTranscriptionResult:
    def test_empty_transcription_result(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        listener.simulate_release()

        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert engine.transcribe_called == 1
        assert injector.injected_texts == []
        pipeline.stop()


@pytest.mark.timeout(10)
class TestWhitespaceOnlyResult:
    def test_whitespace_only_result(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="   \n\t  ")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        listener.simulate_release()

        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert engine.transcribe_called == 1
        assert injector.injected_texts == []
        pipeline.stop()


@pytest.mark.timeout(10)
class TestVeryLongTranscription:
    def test_very_long_transcription(self) -> None:
        long_text = "А" * 10000
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result=long_text)
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        listener.simulate_release()

        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert len(injector.injected_texts) == 1
        assert len(injector.injected_texts[0]) == 10000
        pipeline.stop()


@pytest.mark.timeout(10)
class TestSpecialCharactersInResult:
    def test_special_characters_in_result(self) -> None:
        special_text = (
            "Привет\tмир\nновая строка \"кавычки\" 'одиночные' и $pecial %chars%"
        )
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result=special_text)
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        listener.simulate_release()

        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert injector.injected_texts == [special_text]
        pipeline.stop()


@pytest.mark.timeout(10)
class TestUnicodeEmojiInResult:
    def test_unicode_emoji_in_result(self) -> None:
        emoji_text = "Привет 👋 мир 🌍🎉"
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result=emoji_text)
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        listener.simulate_release()

        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert injector.injected_texts == [emoji_text]
        pipeline.stop()


# ------------------------------------------------------------------
# Injection edge cases
# ------------------------------------------------------------------


@pytest.mark.timeout(10)
class TestInjectorRaisesOnFirstSucceedsOnSecond:
    def test_injector_raises_on_first_succeeds_on_second(self) -> None:
        injector = CountingInjector(fail_until=1)

        pipeline1, sm1, listener1, _, _, _ = _make_pipeline(
            audio=MockAudioCapture(),
            engine=MockRecognitionEngine(transcription_result="Текст для инъекции"),
            injector=injector,
        )

        pipeline1.start()
        listener1.simulate_press()
        listener1.simulate_release()
        assert _wait_for_state(sm1, State.IDLE, timeout=5.0)
        assert len(injector.injected_texts) == 0
        pipeline1.stop()

        pipeline2, sm2, listener2, _, _, _ = _make_pipeline(
            audio=MockAudioCapture(),
            engine=MockRecognitionEngine(transcription_result="Второй текст"),
            injector=injector,
        )
        pipeline2.start()
        listener2.simulate_press()
        listener2.simulate_release()
        assert _wait_for_state(sm2, State.IDLE, timeout=5.0)
        assert injector.injected_texts == ["Второй текст"]
        pipeline2.stop()


@pytest.mark.timeout(10)
class TestInjectionPreservesPipelineState:
    def test_injection_preserves_pipeline_state(self) -> None:
        injector = CountingInjector(fail_until=1)

        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=MockAudioCapture(),
            engine=MockRecognitionEngine(transcription_result="Текст"),
            injector=injector,
        )

        pipeline.start()

        # --- First cycle: injection fails, state must return to IDLE ---
        listener.simulate_press()
        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)

        # Wait until the injector has actually been called
        deadline = time.monotonic() + 3.0
        while injector._inject_count < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert injector._inject_count >= 1

        # Ensure the worker thread has fully finished — including the
        # _handle_error/force_idle call that runs AFTER _inject's finally
        # block transitions to IDLE.  Without this, a late force_idle()
        # can clobber the RECORDING state of the next cycle.
        pipeline._executor.submit(lambda: None).result(timeout=5.0)

        assert len(injector.injected_texts) == 0

        # --- Second cycle: injection succeeds, text is injected ---
        listener.simulate_press()
        assert sm.state == State.RECORDING
        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)

        pipeline._executor.submit(lambda: None).result(timeout=5.0)

        assert injector.injected_texts == ["Текст"]
        pipeline.stop()


# ------------------------------------------------------------------
# Concurrency edge cases
# ------------------------------------------------------------------


@pytest.mark.timeout(10)
class TestHotkeyDuringTranscribing:
    def test_hotkey_during_transcribing(self) -> None:
        transcribe_event = threading.Event()

        class SlowEngine(MockRecognitionEngine):
            def transcribe(self, audio: np.ndarray, language: str = "ru") -> str:
                self.transcribe_called += 1
                self._call_event.set()
                transcribe_event.wait(timeout=3.0)
                if self._transcribe_side_effect is not None:
                    raise self._transcribe_side_effect
                return self._transcription_result

        audio = MockAudioCapture()
        engine = SlowEngine(transcription_result="Медленный текст")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        listener.simulate_release()

        deadline = time.monotonic() + 3.0
        while sm.state != State.TRANSCRIBING and time.monotonic() < deadline:
            time.sleep(0.01)

        if sm.state == State.TRANSCRIBING:
            listener.simulate_press()
            time.sleep(0.1)
            assert sm.state == State.TRANSCRIBING

        transcribe_event.set()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert engine.transcribe_called == 1
        assert len(injector.injected_texts) == 1
        pipeline.stop()


@pytest.mark.timeout(10)
class TestHotkeyDuringInjecting:
    def test_hotkey_during_injecting(self) -> None:
        inject_event = threading.Event()

        class SlowInjector(TextInjector):
            def __init__(self) -> None:
                self.injected_texts: list[str] = []

            def inject(self, text: str) -> None:
                inject_event.wait(timeout=3.0)
                self.injected_texts.append(text)

        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="Текст")
        injector = SlowInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        listener.simulate_release()

        deadline = time.monotonic() + 3.0
        while sm.state != State.INJECTING and time.monotonic() < deadline:
            time.sleep(0.01)

        if sm.state == State.INJECTING:
            listener.simulate_press()
            time.sleep(0.1)
            assert sm.state == State.INJECTING

        inject_event.set()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert len(injector.injected_texts) == 1
        pipeline.stop()


@pytest.mark.timeout(10)
class TestDoubleReleaseIgnored:
    def test_double_release_ignored(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="Двойной релиз")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()
        listener.simulate_press()
        assert sm.state == State.RECORDING

        listener.simulate_release()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)

        assert audio.stop_called == 1
        assert engine.transcribe_called == 1
        assert injector.injected_texts == ["Двойной релиз"]

        listener.simulate_release()
        time.sleep(0.2)
        assert audio.stop_called == 1
        assert engine.transcribe_called == 1
        pipeline.stop()


@pytest.mark.timeout(10)
class TestRapidPressReleaseCycles:
    def test_rapid_press_release_cycles(self) -> None:
        audio = MockAudioCapture()
        engine = MockRecognitionEngine(transcription_result="Цикл")
        injector = MockTextInjector()
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector
        )

        pipeline.start()

        for i in range(3):
            listener.simulate_press()
            assert sm.state == State.RECORDING
            listener.simulate_release()
            assert _wait_for_state(sm, State.IDLE, timeout=5.0), (
                f"Cycle {i} did not complete"
            )

        assert engine.transcribe_called == 3
        assert len(injector.injected_texts) == 3
        pipeline.stop()


# ------------------------------------------------------------------
# Config edge cases
# ------------------------------------------------------------------


@pytest.mark.timeout(10)
class TestConfigChangeDuringRecording:
    def test_config_change_during_recording(self) -> None:
        transcribe_event = threading.Event()

        class SlowEngine(MockRecognitionEngine):
            def transcribe(self, audio: np.ndarray, language: str = "ru") -> str:
                self.transcribe_called += 1
                self._call_event.set()
                transcribe_event.wait(timeout=3.0)
                if self._transcribe_side_effect is not None:
                    raise self._transcribe_side_effect
                return self._transcription_result

        audio = MockAudioCapture()
        engine = SlowEngine(transcription_result="Запись")
        injector = MockTextInjector()
        config = AppConfig(mode="push_to_talk", hotkey="cmd+shift+1", language="ru")
        pipeline, sm, listener, _, _, _ = _make_pipeline(
            audio=audio, engine=engine, injector=injector, config=config
        )

        pipeline.start()
        listener.simulate_press()
        assert sm.state == State.RECORDING

        pipeline.config = AppConfig(
            mode="push_to_talk", hotkey="cmd+shift+1", language="en"
        )

        listener.simulate_release()

        deadline = time.monotonic() + 3.0
        while sm.state != State.TRANSCRIBING and time.monotonic() < deadline:
            time.sleep(0.01)

        transcribe_event.set()
        assert _wait_for_state(sm, State.IDLE, timeout=5.0)
        assert engine.transcribe_called == 1
        assert injector.injected_texts == ["Запись"]

        assert pipeline.config.language == "en"
        pipeline.stop()
