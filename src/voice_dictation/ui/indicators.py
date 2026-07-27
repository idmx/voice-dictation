"""Sound indicators for dictation state changes."""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd
from loguru import logger

_SAMPLE_RATE = 44100


class SoundIndicators:
    """Play sound effects for dictation state changes."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._sounds: dict[str, np.ndarray] = {}
        if enabled:
            self._generate_sounds()

    def play_start(self) -> None:
        """Play recording start sound (short high beep)."""
        self._play(self._sounds.get("start"))

    def play_stop(self) -> None:
        """Play recording stop sound (short low beep)."""
        self._play(self._sounds.get("stop"))

    def play_error(self) -> None:
        """Play error sound (descending tone)."""
        self._play(self._sounds.get("error"))

    def _generate_sounds(self) -> None:
        """Generate beep sounds programmatically using numpy."""
        self._sounds["start"] = self._generate_tone(880, 0.1)
        self._sounds["stop"] = self._generate_tone(440, 0.1)
        self._sounds["error"] = self._generate_descending_tone(660, 330, 0.2)

    @staticmethod
    def _generate_tone(freq: float, duration: float) -> np.ndarray:
        """Generate a single-frequency beep with an envelope."""
        n_samples = int(_SAMPLE_RATE * duration)
        t = np.linspace(0, duration, n_samples, endpoint=False)
        wave = np.sin(2 * np.pi * freq * t)

        attack = int(n_samples * 0.1)
        release = int(n_samples * 0.2)
        envelope = np.ones(n_samples)
        if attack > 0:
            envelope[:attack] = np.linspace(0, 1, attack)
        if release > 0:
            envelope[-release:] = np.linspace(1, 0, release)

        wave = wave * envelope
        wave = (wave * 0.5).astype(np.float32)
        return wave

    @staticmethod
    def _generate_descending_tone(
        start_freq: float, end_freq: float, duration: float
    ) -> np.ndarray:
        """Generate a descending-frequency tone for errors."""
        n_samples = int(_SAMPLE_RATE * duration)
        freqs = np.linspace(start_freq, end_freq, n_samples)
        phase = 2 * np.pi * np.cumsum(freqs) / _SAMPLE_RATE
        wave = np.sin(phase)

        attack = int(n_samples * 0.1)
        release = int(n_samples * 0.2)
        envelope = np.ones(n_samples)
        if attack > 0:
            envelope[:attack] = np.linspace(0, 1, attack)
        if release > 0:
            envelope[-release:] = np.linspace(1, 0, release)

        wave = wave * envelope
        wave = (wave * 0.5).astype(np.float32)
        return wave

    def _play(self, sound: np.ndarray | None) -> None:
        """Play a sound asynchronously."""
        if not self._enabled:
            return
        if sound is None:
            return
        try:
            threading.Thread(
                target=lambda: sd.play(sound, samplerate=_SAMPLE_RATE),
                daemon=True,
            ).start()
        except Exception as e:
            logger.debug(f"Could not play sound: {e}")
