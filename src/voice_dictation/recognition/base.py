"""Abstract base class for recognition engines."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class RecognitionEngine(ABC):
    """Abstract interface for speech recognition implementations."""

    @abstractmethod
    def transcribe(self, audio: np.ndarray, language: str = "ru") -> str:
        """Transcribe audio data to text."""
        ...

    @abstractmethod
    def is_loaded(self) -> bool:
        """Return whether the model is loaded and ready."""
        ...

    @abstractmethod
    def unload(self) -> None:
        """Unload the model and free resources."""
        ...

    @abstractmethod
    def reload(self, model_size: str) -> None:
        """Reload with a different model."""
        ...
