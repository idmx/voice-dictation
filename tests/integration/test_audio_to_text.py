"""Integration tests for audio capture to text recognition pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice_dictation.audio.sounddevice_capture import SoundDeviceCapture
from voice_dictation.recognition.whisper_engine import WhisperEngine


@pytest.fixture
def engine() -> WhisperEngine:
    return WhisperEngine(
        model_size="base",
        device="cpu",
        compute_type="int8",
        model_cache_dir="/tmp/vd-test-integration",
        language="ru",
    )


@pytest.fixture
def capture() -> SoundDeviceCapture:
    return SoundDeviceCapture(sample_rate=16000, channels=1, dtype="int16")


@pytest.fixture
def sample_audio_int16() -> np.ndarray:
    return np.random.randint(-32768, 32767, size=(16000,), dtype=np.int16)


@pytest.fixture
def mock_stream():
    stream = MagicMock()
    stream.start = MagicMock()
    stream.stop = MagicMock()
    stream.close = MagicMock()
    return stream


@pytest.mark.integration
class TestCaptureAndTranscribe:
    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    @patch.object(WhisperEngine, "load")
    def test_capture_and_transcribe(
        self, mock_load, mock_input_stream, engine, capture, mock_stream
    ):
        mock_input_stream.return_value = mock_stream
        capture.start()
        audio_data = np.random.randint(-32768, 32767, size=(16000, 1), dtype=np.int16)
        capture._buffer.append(audio_data)
        result_audio = capture.stop()

        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = "Привет мир"
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine._model = mock_model

        text = engine.transcribe(result_audio)
        assert "Привет мир" in text
        mock_model.transcribe.assert_called_once()

    @patch.object(WhisperEngine, "load")
    def test_different_models_same_audio(self, mock_load, sample_audio_int16):
        results = []
        for model_name in ["tiny", "base", "small"]:
            eng = WhisperEngine(
                model_size=model_name,
                device="cpu",
                compute_type="int8",
                model_cache_dir="/tmp/vd-test-integration",
            )
            mock_model = MagicMock()
            segment = MagicMock()
            segment.text = f"Transcribed by {model_name}"
            mock_model.transcribe.return_value = ([segment], MagicMock())
            eng._model = mock_model
            text = eng.transcribe(sample_audio_int16)
            results.append(text)
        assert len(results) == 3
        assert "tiny" in results[0]
        assert "base" in results[1]
        assert "small" in results[2]

    @patch.object(WhisperEngine, "load")
    def test_language_mismatch(self, mock_load, engine, sample_audio_int16):
        mock_model = MagicMock()
        segment = MagicMock()
        segment.text = "Some transcription result"
        mock_model.transcribe.return_value = ([segment], MagicMock())
        engine._model = mock_model
        text = engine.transcribe(sample_audio_int16, language="en")
        assert isinstance(text, str)
        call_kwargs = mock_model.transcribe.call_args
        assert call_kwargs[1]["language"] == "en"
