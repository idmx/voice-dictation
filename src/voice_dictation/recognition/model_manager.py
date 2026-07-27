"""Model download and cache management."""

from __future__ import annotations

import contextlib
import shutil
import threading
from pathlib import Path

from loguru import logger

from voice_dictation.core.exceptions import ModelNotFoundError

SUPPORTED_MODELS: dict[str, dict[str, int]] = {
    "tiny": {"size_bytes": 75_000_000},
    "base": {"size_bytes": 145_000_000},
    "small": {"size_bytes": 488_000_000},
}


class ModelManager:
    """Manages Whisper model download, caching, and verification."""

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        if cache_dir is None:
            cache_dir = Path.home() / ".voice-dictation" / "models"
        self._cache_dir = Path(cache_dir).expanduser()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._download_locks: dict[str, threading.Lock] = {}
        self._registry_lock = threading.Lock()

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def _get_download_lock(self, model_name: str) -> threading.Lock:
        with self._registry_lock:
            if model_name not in self._download_locks:
                self._download_locks[model_name] = threading.Lock()
            return self._download_locks[model_name]

    def validate_model_name(self, model_size: str) -> str:
        if model_size not in SUPPORTED_MODELS:
            supported = list(SUPPORTED_MODELS.keys())
            raise ModelNotFoundError(
                f"Model '{model_size}' is not supported. Choose from: {supported}"
            )
        return model_size

    def get_available_models(self) -> list[str]:
        return list(SUPPORTED_MODELS.keys())

    def get_model_path(self, model_size: str) -> Path:
        self.validate_model_name(model_size)
        return self._cache_dir / f"model-{model_size}"

    def is_model_cached(self, model_size: str) -> bool:
        path = self.get_model_path(model_size)
        return path.exists() and any(path.iterdir())

    def verify_model(self, model_size: str) -> bool:
        if not self.is_model_cached(model_size):
            return False
        path = self.get_model_path(model_size)
        try:
            total_size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            expected_min = SUPPORTED_MODELS[model_size]["size_bytes"]
            min_acceptable = int(expected_min * 0.5)
            if total_size < min_acceptable:
                logger.warning(
                    f"Model '{model_size}' appears corrupted: "
                    f"size {total_size} < min acceptable {min_acceptable}"
                )
                return False
            return True
        except OSError as e:
            logger.error(f"Error verifying model '{model_size}': {e}")
            return False

    def download_model(self, model_size: str) -> Path:
        self.validate_model_name(model_size)
        download_lock = self._get_download_lock(model_size)
        with download_lock:
            model_path = self.get_model_path(model_size)

            if self.is_model_cached(model_size) and self.verify_model(model_size):
                logger.info(f"Model '{model_size}' already cached at {model_path}")
                return model_path

            if self.is_model_cached(model_size) and not self.verify_model(model_size):
                logger.warning(f"Corrupted model '{model_size}', removing and re-downloading")
                self.remove_model(model_size)

            logger.info(f"Downloading model '{model_size}'...")
            try:
                from faster_whisper import download_model as fw_download

                downloaded_path = fw_download(model_size, output_dir=str(model_path))
                logger.info(f"Model '{model_size}' downloaded to {downloaded_path}")
                return Path(downloaded_path)
            except Exception as e:
                if model_path.exists():
                    shutil.rmtree(model_path, ignore_errors=True)
                raise ModelNotFoundError(f"Failed to download model '{model_size}': {e}") from e

    def remove_model(self, model_size: str) -> None:
        model_path = self.get_model_path(model_size)
        if model_path.exists():
            shutil.rmtree(model_path)
            logger.info(f"Removed model '{model_size}' from cache")
        else:
            logger.warning(f"Model '{model_size}' not found in cache for removal")

    def clear_cache(self) -> None:
        if self._cache_dir.exists():
            for entry in self._cache_dir.iterdir():
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
            logger.info(f"Cleared model cache at {self._cache_dir}")

    def get_cache_size(self) -> int:
        if not self._cache_dir.exists():
            return 0
        total = 0
        for f in self._cache_dir.rglob("*"):
            if f.is_file():
                with contextlib.suppress(OSError):
                    total += f.stat().st_size
        return total

    @staticmethod
    def list_supported_models() -> list[str]:
        return list(SUPPORTED_MODELS.keys())
