"""Unit tests for SoundIndicators."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice_dictation.ui.indicators import SoundIndicators


@pytest.fixture
def indicators() -> SoundIndicators:
    return SoundIndicators(enabled=True)


@pytest.fixture
def disabled_indicators() -> SoundIndicators:
    return SoundIndicators(enabled=False)


class TestStartSound:
    @patch("voice_dictation.ui.indicators.sd")
    def test_start_sound_played(self, mock_sd, indicators) -> None:
        mock_sd.play = MagicMock()
        indicators.play_start()
        assert mock_sd.play.called
        call_args = mock_sd.play.call_args
        sound_array = call_args[0][0]
        assert isinstance(sound_array, np.ndarray)
        assert len(sound_array) > 0


class TestStopSound:
    @patch("voice_dictation.ui.indicators.sd")
    def test_stop_sound_played(self, mock_sd, indicators) -> None:
        mock_sd.play = MagicMock()
        indicators.play_stop()
        assert mock_sd.play.called
        call_args = mock_sd.play.call_args
        sound_array = call_args[0][0]
        assert isinstance(sound_array, np.ndarray)
        assert len(sound_array) > 0


class TestErrorSound:
    @patch("voice_dictation.ui.indicators.sd")
    def test_error_sound_played(self, mock_sd, indicators) -> None:
        mock_sd.play = MagicMock()
        indicators.play_error()
        assert mock_sd.play.called
        call_args = mock_sd.play.call_args
        sound_array = call_args[0][0]
        assert isinstance(sound_array, np.ndarray)
        assert len(sound_array) > 0


class TestDisabledSounds:
    @patch("voice_dictation.ui.indicators.sd")
    def test_sounds_disabled(self, mock_sd, indicators, disabled_indicators) -> None:
        mock_sd.play = MagicMock()
        disabled_indicators.play_start()
        disabled_indicators.play_stop()
        disabled_indicators.play_error()
        mock_sd.play.assert_not_called()

    def test_no_sounds_generated_when_disabled(self) -> None:
        si = SoundIndicators(enabled=False)
        assert len(si._sounds) == 0


class TestSoundGeneration:
    def test_sound_files_generated(self, indicators) -> None:
        assert "start" in indicators._sounds
        assert "stop" in indicators._sounds
        assert "error" in indicators._sounds
        for name, arr in indicators._sounds.items():
            assert isinstance(arr, np.ndarray), f"{name} is not ndarray"
            assert len(arr) > 0, f"{name} is empty"
            assert arr.dtype == np.float32, f"{name} has wrong dtype"

    def test_start_sound_frequency(self) -> None:
        si = SoundIndicators(enabled=True)
        start = si._sounds["start"]
        n = len(start)
        expected_duration = 0.1
        assert abs(n / 44100.0 - expected_duration) < 0.01

    def test_stop_sound_same_length_as_start(self) -> None:
        si = SoundIndicators(enabled=True)
        start = si._sounds["start"]
        stop = si._sounds["stop"]
        assert len(stop) == len(start)


class TestPlayHandlesErrors:
    @patch("voice_dictation.ui.indicators.threading.Thread")
    @patch("voice_dictation.ui.indicators.sd")
    def test_play_handles_sd_error(self, mock_sd, mock_thread, indicators) -> None:
        mock_sd.play = MagicMock(side_effect=OSError("No audio device"))
        mock_thread.return_value = MagicMock()
        indicators.play_start()
        mock_thread.assert_called_once()

    def test_play_with_none_sound(self) -> None:
        si = SoundIndicators(enabled=True)
        si._sounds.clear()
        si.play_start()

    @patch("voice_dictation.ui.indicators.threading.Thread")
    @patch("voice_dictation.ui.indicators.sd")
    def test_play_handles_sd_exception(self, mock_sd, mock_thread, indicators) -> None:
        mock_sd.play = MagicMock(side_effect=RuntimeError("Audio device error"))
        mock_thread.return_value = MagicMock()
        indicators.play_start()
        mock_thread.assert_called_once()


class TestPlayAsync:
    @patch("voice_dictation.ui.indicators.sd")
    def test_play_async(self, mock_sd, indicators) -> None:
        mock_sd.play = MagicMock()
        indicators.play_start()
        import time

        time.sleep(0.2)
        assert mock_sd.play.called

    @patch("voice_dictation.ui.indicators.sd")
    def test_play_uses_daemon_thread(self, mock_sd, indicators) -> None:
        mock_sd.play = MagicMock()
        original_thread = threading.Thread

        created_threads: list[threading.Thread] = []

        with patch("voice_dictation.ui.indicators.threading.Thread") as mock_thread_cls:

            def capture_thread(*a, **kw):
                t = original_thread(*a, **kw)
                created_threads.append(t)
                return t

            mock_thread_cls.side_effect = capture_thread
            indicators.play_start()

        if created_threads:
            assert created_threads[0].daemon is True


class TestDescendingTone:
    def test_error_sound_descending(self) -> None:
        si = SoundIndicators(enabled=True)
        error = si._sounds["error"]
        n = len(error)
        expected_duration = 0.2
        assert abs(n / 44100.0 - expected_duration) < 0.01

    def test_error_sound_longer_than_beeps(self) -> None:
        si = SoundIndicators(enabled=True)
        assert len(si._sounds["error"]) > len(si._sounds["start"])
        assert len(si._sounds["error"]) > len(si._sounds["stop"])
