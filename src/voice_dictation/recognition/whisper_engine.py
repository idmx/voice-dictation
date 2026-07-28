"""Faster-Whisper based recognition engine."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel
from loguru import logger

from voice_dictation.core.exceptions import ModelLoadError, TranscriptionError
from voice_dictation.recognition.base import RecognitionEngine
from voice_dictation.recognition.model_manager import ModelManager


class WhisperEngine(RecognitionEngine):
    """Speech recognition using faster-whisper."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "ru",
        initial_prompt: str = "",
        model_cache_dir: str | None = None,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._initial_prompt = initial_prompt
        self._model = None
        self._model_manager = ModelManager(cache_dir=model_cache_dir)
        self._load_lock = threading.Lock()
        self._progress_callback: Callable[[int], None] | None = None

    def is_loaded(self) -> bool:
        return self._model is not None

    def set_progress_callback(self, callback: Callable[[int], None]) -> None:
        """Set a callback for download progress reporting (0-100%)."""
        self._progress_callback = callback

    def _load_model(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            try:
                if self._model_manager.is_model_cached(self._model_size) and \
                   self._model_manager.verify_model(self._model_size):
                    model_path = self._model_manager.get_model_path(self._model_size)
                    # faster-whisper downloads to a subdirectory; find the
                    # directory that actually contains model.bin
                    actual_path = self._find_model_dir(model_path)
                    logger.info(f"Loading cached model '{self._model_size}' from {actual_path}")
                    self._model = WhisperModel(
                        str(actual_path),
                        device=self._device,
                        compute_type=self._compute_type,
                    )
                else:
                    logger.info(f"Downloading and loading model '{self._model_size}'")
                    downloaded_path = self._model_manager.download_model(
                        self._model_size,
                        progress_callback=self._progress_callback,
                    )
                    actual_path = self._find_model_dir(Path(downloaded_path))
                    self._model = WhisperModel(
                        str(actual_path),
                        device=self._device,
                        compute_type=self._compute_type,
                    )
                logger.info(f"Model '{self._model_size}' loaded successfully")
            except (ModelLoadError, TranscriptionError):
                raise
            except Exception as e:
                self._model = None
                raise ModelLoadError(f"Failed to load model '{self._model_size}': {e}") from e

    @staticmethod
    def _find_model_dir(base_path: Path) -> Path:
        """Find the directory containing model.bin.

        faster-whisper downloads models to a nested subdirectory
        (e.g. model-medium/models--Systran--faster-whisper-medium/snapshots/xxx/).
        WhisperModel expects the path to the directory containing model.bin.
        """
        # Direct hit
        if (base_path / "model.bin").exists():
            return base_path
        # Search subdirectories
        for model_bin in base_path.rglob("model.bin"):
            return model_bin.parent
        # Fallback — return base_path and let WhisperModel fail with a clear error
        logger.warning(f"model.bin not found under {base_path}")
        return base_path

    def load(self) -> None:
        self._load_model()

    def unload(self) -> None:
        with self._load_lock:
            if self._model is not None:
                # Explicitly delete the model to free memory (including GPU/CUDA).
                # Simply setting to None may not release CTranslate2's internal
                # caches and CUDA allocations.
                try:
                    del self._model
                except Exception:
                    pass
                self._model = None
                # Attempt to release CUDA memory if torch is available
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass
                logger.info(f"Model '{self._model_size}' unloaded")

    def reload(self, model_size: str) -> None:
        logger.info(f"Reloading model: {self._model_size} -> {model_size}")
        self.unload()
        self._model_size = model_size
        try:
            self._load_model()
            if self._model is not None:
                logger.info(f"Model '{model_size}' loaded successfully")
            else:
                logger.error(f"Model '{model_size}' failed to load — _model is None")
        except Exception as e:
            logger.error(f"Model '{model_size}' reload failed: {e}")
            # Don't re-raise — the old model is unloaded, but we don't
            # want to crash the background thread. Next transcription
            # will attempt to load again via transcribe() -> _load_model().

    @staticmethod
    def _int16_to_float32(audio: np.ndarray) -> np.ndarray:
        if audio.dtype == np.int16:
            return audio.astype(np.float32) / 32768.0
        if audio.dtype == np.float32:
            return audio
        return audio.astype(np.float32) / 32768.0

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> str:
        if audio.size == 0:
            logger.warning("Empty audio data received for transcription")
            return ""

        if self._model is None:
            self._load_model()

        if self._model is None:
            raise TranscriptionError("Model could not be loaded")

        audio_float32 = self._int16_to_float32(audio)
        if audio_float32.ndim > 1:
            audio_float32 = audio_float32.squeeze()

        lang = language or self._language

        try:
            segments, _info = self._model.transcribe(
                audio_float32,
                beam_size=5,
                language=lang,
                initial_prompt=self._initial_prompt if self._initial_prompt else None,
                vad_filter=False,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
            logger.debug(f"Transcribed ({lang}): {text[:80]}{'...' if len(text) > 80 else ''}")
            return text
        except Exception as e:
            raise TranscriptionError(f"Transcription failed: {e}") from e
