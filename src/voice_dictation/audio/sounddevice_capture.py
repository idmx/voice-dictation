"""Sounddevice-based audio capture implementation."""

from __future__ import annotations

import threading
from typing import Any

import numpy as np
import sounddevice as sd
from loguru import logger

from voice_dictation.audio.base import AudioCapture
from voice_dictation.core.exceptions import (
    AlreadyRecordingError,
    AudioDeviceError,
    NotRecordingError,
)


class SoundDeviceCapture(AudioCapture):
    """Audio capture using sounddevice InputStream."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        dtype: str = "int16",
        device_index: int | None = None,
        blocksize: int = 0,
    ) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._dtype = dtype
        self._device_index = device_index
        self._blocksize = blocksize
        self._stream: sd.InputStream | None = None
        self._buffer: list[np.ndarray] = []
        self._recording = False
        self._lock = threading.Lock()

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.warning(f"Audio callback status: {status}")
        self._buffer.append(indata.copy())

    def start(self) -> None:
        with self._lock:
            if self._recording:
                raise AlreadyRecordingError("Already recording")
            self._buffer = []
            try:
                self._stream = sd.InputStream(
                    samplerate=self._sample_rate,
                    channels=self._channels,
                    dtype=self._dtype,
                    device=self._device_index,
                    blocksize=self._blocksize,
                    callback=self._audio_callback,
                )
                self._stream.start()
                self._recording = True
                logger.debug(
                    f"Audio capture started: {self._sample_rate}Hz, "
                    f"{self._channels}ch, {self._dtype}"
                )
            except OSError as e:
                self._stream = None
                raise AudioDeviceError(f"Failed to start audio stream: {e}") from e
            except sd.PortAudioError as e:
                self._stream = None
                raise AudioDeviceError(f"Failed to start audio stream: {e}") from e

    def stop(self) -> np.ndarray:
        with self._lock:
            if not self._recording:
                raise NotRecordingError("Not recording")
            self._recording = False
            try:
                if self._stream is not None:
                    self._stream.stop()
                    self._stream.close()
            except (sd.PortAudioError, OSError) as e:
                logger.error(f"Error stopping audio stream: {e}")
            finally:
                self._stream = None
            if self._buffer:
                result = np.concatenate(self._buffer, axis=0)
            else:
                result = np.empty((0, self._channels), dtype=self._dtype)
            self._buffer = []
            logger.debug(f"Audio capture stopped, got {result.shape[0]} samples")
            return result

    def is_recording(self) -> bool:
        return self._recording

    def get_devices(self) -> list[dict[str, Any]]:
        try:
            devices = sd.query_devices()
            input_devices: list[dict[str, Any]] = []
            for i, dev in enumerate(devices):
                if dev["max_input_channels"] > 0:
                    input_devices.append({
                        "index": i,
                        "name": dev["name"],
                        "sample_rate": dev["default_samplerate"],
                        "max_channels": dev["max_input_channels"],
                    })
            return input_devices
        except (sd.PortAudioError, OSError) as e:
            raise AudioDeviceError(f"Failed to enumerate audio devices: {e}") from e

    @staticmethod
    def list_devices() -> list[dict[str, Any]]:
        try:
            devices = sd.query_devices()
            input_devices: list[dict[str, Any]] = []
            for i, dev in enumerate(devices):
                if dev["max_input_channels"] > 0:
                    input_devices.append({
                        "index": i,
                        "name": dev["name"],
                        "sample_rate": dev["default_samplerate"],
                        "max_channels": dev["max_input_channels"],
                    })
            return input_devices
        except (sd.PortAudioError, OSError) as e:
            raise AudioDeviceError(f"Failed to enumerate audio devices: {e}") from e

    def __del__(self) -> None:
        try:
            if self._recording and self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._recording = False
        except Exception:
            pass
