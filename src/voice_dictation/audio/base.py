"""Abstract base class for audio capture."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class AudioCapture(ABC):
    """Abstract interface for audio capture implementations."""

    @abstractmethod
    def start(self) -> None:
        """Start recording audio."""
        ...

    @abstractmethod
    def stop(self) -> np.ndarray:
        """Stop recording and return captured audio as int16 numpy array (16kHz, mono)."""
        ...

    @abstractmethod
    def is_recording(self) -> bool:
        """Return whether currently recording."""
        ...

    @abstractmethod
    def get_devices(self) -> list[dict[str, Any]]:
        """List available audio input devices."""
        ...
