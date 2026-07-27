"""Unit tests for WhisperEngine."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice_dictation.core.exceptions import ModelLoadError, TranscriptionError
from voice_dictation.recognition.whisper_engine import WhisperEngine


@pytest.fixture
def engine() -> WhisperEngine:
    return WhisperEngine(
        model_size="base",
        device="cpu",
        compute_type="int8",
        model_cache_dir="/tmp/vd-test-models",
        language="ru",
        initial_prompt="",
    )


@pytest.fixture
def mock_whisper_model():
    model = MagicMock()
    segment1 = MagicMock()
    segment1.text = "Привет мир"
    segment2 = MagicMock()
    segment2.text = " как дела"
    model.transcribe.return_value = ([segment1, segment2], MagicMock())
    return model


@pytest.fixture
def sample_audio_int16() -> np.ndarray:
    return np.random.randint(-32768, 32767, size=(16000,), dtype=np.int16)


@pytest.fixture
def silence_audio_int16() -> np.ndarray:
    return np.zeros(16000, dtype=np.int16)


class TestTranscribe:
    @patch.object(WhisperEngine, "load")
    def test_transcribe_russian_short(
        self, mock_load, engine, mock_whisper_model, sample_audio_int16
    ):
        engine._model = mock_whisper_model
        result = engine.transcribe(sample_audio_int16, language="ru")
        assert "Привет мир" in result
        assert "как дела" in result

    @patch.object(WhisperEngine, "load")
    def test_transcribe_silence(self, mock_load, engine, silence_audio_int16):
        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = ""
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine._model = mock_model
        result = engine.transcribe(silence_audio_int16)
        assert isinstance(result, str)

    @patch.object(WhisperEngine, "load")
    def test_transcribe_with_language_param(self, mock_load, engine, sample_audio_int16):
        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = "Hello world"
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine._model = mock_model
        engine.transcribe(sample_audio_int16, language="en")
        mock_model.transcribe.assert_called_once()
        call_kwargs = mock_model.transcribe.call_args
        assert call_kwargs[1]["language"] == "en"

    @patch.object(WhisperEngine, "load")
    def test_transcribe_with_initial_prompt(self, mock_load, sample_audio_int16):
        engine_with_prompt = WhisperEngine(
            model_size="base",
            device="cpu",
            compute_type="int8",
            model_cache_dir="/tmp/vd-test-models",
            initial_prompt="Контекст на русском",
        )
        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = "Текст"
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine_with_prompt._model = mock_model
        engine_with_prompt.transcribe(sample_audio_int16)
        call_kwargs = mock_model.transcribe.call_args
        assert call_kwargs[1]["initial_prompt"] == "Контекст на русском"

    def test_transcribe_empty_audio(self, engine):
        empty = np.array([], dtype=np.int16)
        result = engine.transcribe(empty)
        assert result == ""

    @patch.object(WhisperEngine, "load")
    def test_transcribe_timeout(self, mock_load, engine, sample_audio_int16):
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = TimeoutError("transcription timed out")
        engine._model = mock_model
        with pytest.raises(TranscriptionError, match="Transcription failed"):
            engine.transcribe(sample_audio_int16)

    @patch.object(WhisperEngine, "load")
    def test_vad_filter(self, mock_load, engine, sample_audio_int16):
        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = "test"
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine._model = mock_model
        engine.transcribe(sample_audio_int16)
        call_kwargs = mock_model.transcribe.call_args
        assert call_kwargs[1]["vad_filter"] is True

    @patch.object(WhisperEngine, "load")
    def test_transcribe_error(self, mock_load, engine, sample_audio_int16):
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = RuntimeError("model error")
        engine._model = mock_model
        with pytest.raises(TranscriptionError):
            engine.transcribe(sample_audio_int16)

    @patch.object(WhisperEngine, "load")
    def test_audio_conversion(self, mock_load, engine, sample_audio_int16):
        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = "test"
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine._model = mock_model
        engine.transcribe(sample_audio_int16)
        call_args = mock_model.transcribe.call_args[0][0]
        assert call_args.dtype == np.float32
        assert np.all(call_args >= -1.0) and np.all(call_args <= 1.0)

    @patch.object(WhisperEngine, "load")
    def test_transcribe_returns_text_not_segments(self, mock_load, engine, sample_audio_int16):
        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = "Hello"
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine._model = mock_model
        result = engine.transcribe(sample_audio_int16)
        assert isinstance(result, str)


class TestModelLifecycle:
    def test_model_lazy_load(self, engine):
        assert not engine.is_loaded()

    @patch.object(WhisperEngine, "load")
    def test_is_loaded_false_initially(self, mock_load):
        eng = WhisperEngine(
            model_size="base",
            device="cpu",
            compute_type="int8",
            model_cache_dir="/tmp/vd-test-models",
        )
        assert not eng.is_loaded()

    @patch.object(WhisperEngine, "load")
    def test_is_loaded_true_after_transcribe(self, mock_load, engine, sample_audio_int16):
        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = "test"
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine._model = mock_model
        engine.transcribe(sample_audio_int16)
        assert engine.is_loaded()

    def test_unload(self, engine):
        engine._model = MagicMock()
        assert engine.is_loaded()
        engine.unload()
        assert not engine.is_loaded()

    @patch("voice_dictation.recognition.whisper_engine.WhisperModel")
    def test_reload(self, mock_model_cls, engine):
        with patch.object(engine._model_manager, "is_model_cached", return_value=True):
            engine._model = MagicMock()
            mock_model_cls.return_value = MagicMock()
            engine.reload("tiny")
            assert engine._model_size == "tiny"

    @patch("voice_dictation.recognition.whisper_engine.WhisperModel")
    def test_explicit_load_unload(self, mock_model_cls, engine):
        with patch.object(engine._model_manager, "is_model_cached", return_value=True):
            engine._model = None
            mock_model_cls.return_value = MagicMock()
            engine.load()
            assert engine.is_loaded()
        engine.unload()
        assert not engine.is_loaded()

    @patch("voice_dictation.recognition.whisper_engine.WhisperModel")
    def test_load_failure(self, mock_model_cls, engine):
        mock_model_cls.side_effect = RuntimeError("load failed")
        with (
            patch.object(engine._model_manager, "is_model_cached", return_value=True),
            pytest.raises(ModelLoadError),
        ):
            engine.load()
        assert not engine.is_loaded()

    @patch("voice_dictation.recognition.whisper_engine.WhisperModel")
    def test_load_already_loaded(self, mock_model_cls, engine):
        engine._model = MagicMock()
        engine.load()
        mock_model_cls.assert_not_called()


class TestInt16ToFloat32:
    def test_int16_to_float32_conversion(self):
        audio_int16 = np.array([32767, -32768, 0, 16384], dtype=np.int16)
        result = WhisperEngine._int16_to_float32(audio_int16)
        assert result.dtype == np.float32
        assert np.isclose(result[0], 1.0, atol=1e-4)
        assert np.isclose(result[1], -1.0, atol=1e-4)
        assert np.isclose(result[2], 0.0, atol=1e-4)
        assert np.isclose(result[3], 0.5, atol=1e-2)

    def test_float32_passthrough(self):
        audio_float = np.array([0.5, -0.5, 0.0], dtype=np.float32)
        result = WhisperEngine._int16_to_float32(audio_float)
        assert result.dtype == np.float32
        np.testing.assert_array_equal(result, audio_float)

    @patch.object(WhisperEngine, "load")
    def test_multichannel_squeeze(self, mock_load, engine):
        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = "test"
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine._model = mock_model
        audio_2d = np.zeros((16000, 1), dtype=np.int16)
        engine.transcribe(audio_2d)
        call_args = mock_model.transcribe.call_args[0][0]
        assert call_args.ndim == 1


class TestWAVFixture:
    @patch.object(WhisperEngine, "load")
    def test_transcribe_from_wav_file(self, mock_load, engine, fixtures_dir):
        wav_path = fixtures_dir / "audio_samples" / "silence.wav"
        if not wav_path.exists():
            pytest.skip("WAV fixture not found")
        import wave

        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16)
        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = ""
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine._model = mock_model
        result = engine.transcribe(audio)
        assert isinstance(result, str)


class TestThreadSafety:
    @patch.object(WhisperEngine, "load")
    def test_concurrent_transcribe(self, mock_load, engine, sample_audio_int16):
        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = "test"
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine._model = mock_model

        results: list[str] = []
        errors: list[Exception] = []

        def do_transcribe():
            try:
                r = engine.transcribe(sample_audio_int16)
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_transcribe) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        assert len(results) == 5
