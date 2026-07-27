"""Faster-Whisper based recognition engine."""

from __future__ import annotations

import threading

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

    def is_loaded(self) -> bool:
        return self._model is not None

    def _load_model(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            try:
                model_path = self._model_manager.get_model_path(self._model_size)
                if self._model_manager.is_model_cached(self._model_size):
                    logger.info(f"Loading cached model '{self._model_size}' from {model_path}")
                    self._model = WhisperModel(
                        str(model_path),
                        device=self._device,
                        compute_type=self._compute_type,
                    )
                else:
                    logger.info(f"Downloading and loading model '{self._model_size}'")
                    downloaded_path = self._model_manager.download_model(self._model_size)
                    self._model = WhisperModel(
                        str(downloaded_path),
                        device=self._device,
                        compute_type=self._compute_type,
                    )
                logger.info(f"Model '{self._model_size}' loaded successfully")
            except (ModelLoadError, TranscriptionError):
                raise
            except Exception as e:
                self._model = None
                raise ModelLoadError(
                    f"Failed to load model '{self._model_size}': {e}"
                ) from e

    def load(self) -> None:
        self._load_model()

    def unload(self) -> None:
        with self._load_lock:
            if self._model is not None:
                self._model = None
                logger.info(f"Model '{self._model_size}' unloaded")

    def reload(self, model_size: str) -> None:
        self.unload()
        self._model_size = model_size
        self._load_model()

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
                vad_filter=True,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
            logger.debug(
                f"Transcribed ({lang}): {text[:80]}{'...' if len(text) > 80 else ''}"
            )
            return text
        except Exception as e:
            raise TranscriptionError(f"Transcription failed: {e}") from e
