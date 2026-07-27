"""Unit tests for SoundDeviceCapture."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import sounddevice as sd

from voice_dictation.audio.sounddevice_capture import SoundDeviceCapture
from voice_dictation.core.exceptions import (
    AlreadyRecordingError,
    AudioDeviceError,
    NotRecordingError,
)


@pytest.fixture
def capture() -> SoundDeviceCapture:
    return SoundDeviceCapture(sample_rate=16000, channels=1, dtype="int16")


@pytest.fixture
def capture_with_device() -> SoundDeviceCapture:
    return SoundDeviceCapture(sample_rate=16000, channels=1, dtype="int16", device_index=99)


@pytest.fixture
def mock_stream():
    stream = MagicMock()
    stream.start = MagicMock()
    stream.stop = MagicMock()
    stream.close = MagicMock()
    return stream


class TestStartRecording:
    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_start_recording(self, mock_input_stream, capture, mock_stream):
        mock_input_stream.return_value = mock_stream
        capture.start()
        mock_input_stream.assert_called_once_with(
            samplerate=16000,
            channels=1,
            dtype="int16",
            device=None,
            blocksize=0,
            callback=capture._audio_callback,
        )
        mock_stream.start.assert_called_once()
        assert capture.is_recording()


class TestStopRecording:
    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_stop_returns_numpy_array(self, mock_input_stream, capture, mock_stream):
        mock_input_stream.return_value = mock_stream
        capture.start()
        capture._buffer.append(np.array([[100], [200]], dtype=np.int16))
        result = capture.stop()
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.int16

    def test_stop_when_not_recording(self, capture):
        with pytest.raises(NotRecordingError):
            capture.stop()

    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_double_start(self, mock_input_stream, capture, mock_stream):
        mock_input_stream.return_value = mock_stream
        capture.start()
        with pytest.raises(AlreadyRecordingError):
            capture.start()


class TestRecordingDuration:
    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_recording_duration(self, mock_input_stream, capture, mock_stream):
        mock_input_stream.return_value = mock_stream
        capture.start()
        samples = np.zeros((32000, 1), dtype=np.int16)
        capture._buffer.append(samples)
        result = capture.stop()
        assert result.shape[0] == 32000


class TestSilenceDetection:
    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_silence_detection(self, mock_input_stream, capture, mock_stream):
        mock_input_stream.return_value = mock_stream
        capture.start()
        silence = np.zeros((16000, 1), dtype=np.int16)
        capture._buffer.append(silence)
        result = capture.stop()
        assert np.allclose(result, 0)


class TestIsRecording:
    def test_is_recording_false_initially(self, capture):
        assert not capture.is_recording()

    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_is_recording_true_after_start(self, mock_input_stream, capture, mock_stream):
        mock_input_stream.return_value = mock_stream
        capture.start()
        assert capture.is_recording()

    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_is_recording_false_after_stop(self, mock_input_stream, capture, mock_stream):
        mock_input_stream.return_value = mock_stream
        capture.start()
        capture._buffer.append(np.zeros((100, 1), dtype=np.int16))
        capture.stop()
        assert not capture.is_recording()


class TestGetDevices:
    @patch("voice_dictation.audio.sounddevice_capture.sd.query_devices")
    def test_get_devices(self, mock_query_devices):
        mock_query_devices.return_value = [
            {"name": "Mic", "max_input_channels": 2, "default_samplerate": 44100},
            {"name": "Speaker", "max_input_channels": 0, "default_samplerate": 48000},
            {"name": "USB Mic", "max_input_channels": 1, "default_samplerate": 16000},
        ]
        devices = SoundDeviceCapture().get_devices()
        assert len(devices) == 2
        assert devices[0]["name"] == "Mic"
        assert devices[1]["name"] == "USB Mic"

    @patch("voice_dictation.audio.sounddevice_capture.sd.query_devices")
    def test_get_devices_empty(self, mock_query_devices):
        mock_query_devices.return_value = []
        devices = SoundDeviceCapture().get_devices()
        assert devices == []


class TestDeviceErrors:
    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_no_microphone(self, mock_input_stream, capture):
        mock_input_stream.side_effect = OSError("No device found")
        with pytest.raises(AudioDeviceError):
            capture.start()

    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_invalid_device_index(self, mock_input_stream, capture_with_device):
        mock_input_stream.side_effect = OSError("Invalid device index")
        with pytest.raises(AudioDeviceError):
            capture_with_device.start()

    @patch("voice_dictation.audio.sounddevice_capture.sd.query_devices")
    def test_list_devices_error(self, mock_query_devices):
        mock_query_devices.side_effect = sd.PortAudioError("PortAudio error")
        with pytest.raises(AudioDeviceError):
            SoundDeviceCapture.list_devices()


class TestAudioCallback:
    def test_callback_appends_data(self, capture):
        indata = np.array([[100], [200]], dtype=np.int16)
        capture._audio_callback(indata, 2, None, None)
        assert len(capture._buffer) == 1
        np.testing.assert_array_equal(capture._buffer[0], indata)

    def test_callback_with_status(self, capture):
        indata = np.array([[50]], dtype=np.int16)
        status = MagicMock()
        capture._audio_callback(indata, 1, None, status)

    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_stop_concats_buffer(self, mock_input_stream, capture, mock_stream):
        mock_input_stream.return_value = mock_stream
        capture.start()
        chunk1 = np.array([[100], [200]], dtype=np.int16)
        chunk2 = np.array([[300], [400]], dtype=np.int16)
        capture._buffer.append(chunk1)
        capture._buffer.append(chunk2)
        result = capture.stop()
        expected = np.concatenate([chunk1, chunk2], axis=0)
        np.testing.assert_array_equal(result, expected)

    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_stop_empty_buffer(self, mock_input_stream, capture, mock_stream):
        mock_input_stream.return_value = mock_stream
        capture.start()
        result = capture.stop()
        assert result.shape[0] == 0

    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_stop_stream_error_handled(self, mock_input_stream, capture, mock_stream):
        mock_input_stream.return_value = mock_stream
        capture.start()
        capture._buffer.append(np.zeros((100, 1), dtype=np.int16))
        mock_stream.stop.side_effect = sd.PortAudioError("stop error")
        result = capture.stop()
        assert result.shape[0] == 100


class TestCleanup:
    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_cleanup_on_del(self, mock_input_stream, mock_stream):
        mock_input_stream.return_value = mock_stream
        cap = SoundDeviceCapture()
        cap.start()
        assert cap.is_recording()
        cap.__del__()
        mock_stream.stop.assert_called()
        mock_stream.close.assert_called()
        assert not cap._recording


class TestThreadSafety:
    @patch("voice_dictation.audio.sounddevice_capture.sd.InputStream")
    def test_thread_safety(self, mock_input_stream, capture, mock_stream):
        mock_input_stream.return_value = mock_stream
        errors: list[Exception] = []

        def try_start():
            try:
                capture.start()
            except AlreadyRecordingError:
                errors.append(AlreadyRecordingError("already recording"))

        t1 = threading.Thread(target=try_start)
        t2 = threading.Thread(target=try_start)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(errors) == 1
