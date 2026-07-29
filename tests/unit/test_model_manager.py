"""Unit tests for ModelManager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voice_dictation.core.exceptions import ModelNotFoundError
from voice_dictation.recognition.model_manager import ModelManager


@pytest.fixture
def model_manager(tmp_path: Path) -> ModelManager:
    cache_dir = tmp_path / "models"
    return ModelManager(cache_dir=cache_dir)


@pytest.fixture
def cached_model_manager(model_manager: ModelManager) -> ModelManager:
    model_path = model_manager.get_model_path("tiny")
    model_path.mkdir(parents=True)
    (model_path / "model.bin").write_bytes(b"\x00" * 80_000_000)
    return model_manager


class TestDownloadModel:
    @patch("voice_dictation.recognition.model_manager.fw_download", create=True)
    def test_download_model(self, mock_download, model_manager, tmp_path):
        model_dir = model_manager.get_model_path("tiny")
        model_dir.mkdir(parents=True)
        (model_dir / "model.bin").write_bytes(b"\x00" * 80_000_000)
        mock_download.return_value = str(model_dir)
        with (
            patch.dict("sys.modules", {"faster_whisper": MagicMock(download_model=mock_download)}),
            patch.object(model_manager, "is_model_cached", return_value=True),
            patch.object(model_manager, "verify_model", return_value=True),
        ):
            model_manager.download_model("tiny")
            assert model_manager.is_model_cached("tiny")

    def test_model_already_cached(self, cached_model_manager):
        with patch.object(cached_model_manager, "verify_model", return_value=True):
            result = cached_model_manager.download_model("tiny")
            assert result.exists()

    def test_corrupted_model_redownloads(self, model_manager):
        model_path = model_manager.get_model_path("tiny")
        model_path.mkdir(parents=True)
        (model_path / "model.bin").write_bytes(b"\x00" * 100)
        mock_dl = MagicMock()
        new_path = model_manager.get_model_path("tiny")
        mock_dl.return_value = str(new_path)
        new_path.mkdir(parents=True, exist_ok=True)
        (new_path / "model.bin").write_bytes(b"\x00" * 80_000_000)
        with (
            patch.dict("sys.modules", {"faster_whisper": MagicMock(download_model=mock_dl)}),
            patch.object(model_manager, "is_model_cached", side_effect=[True, False, True]),
            patch.object(model_manager, "verify_model", side_effect=[False, True]),
        ):
            model_manager.download_model("tiny")

    def test_invalid_model_name(self, model_manager):
        with pytest.raises(ModelNotFoundError):
            model_manager.download_model("mega")

    def test_download_failure_cleanup(self, model_manager):
        model_path = model_manager.get_model_path("tiny")
        model_path.mkdir(parents=True)
        (model_path / "partial.incomplete").write_bytes(b"\x00" * 100)

        with (
            patch.object(model_manager, "is_model_cached", return_value=False),
            patch.object(
                model_manager,
                "_download_with_progress",
                side_effect=RuntimeError("download failed"),
            ),
            pytest.raises(ModelNotFoundError, match="Failed to download"),
        ):
            model_manager.download_model("tiny")

        assert not model_path.exists()


class TestModelInfo:
    def test_get_model_path(self, model_manager):
        path = model_manager.get_model_path("tiny")
        assert path.name == "model-tiny"

    def test_get_model_path_invalid(self, model_manager):
        with pytest.raises(ModelNotFoundError):
            model_manager.get_model_path("nonexistent")


class TestAvailableModels:
    def test_get_available_models(self, model_manager):
        models = model_manager.get_available_models()
        assert models == ["tiny", "base", "small", "medium"]

    def test_list_supported_models(self):
        models = ModelManager.list_supported_models()
        assert "tiny" in models
        assert "base" in models
        assert "small" in models


class TestValidateModelName:
    def test_validate_model_name_valid(self, model_manager):
        assert model_manager.validate_model_name("base") == "base"

    def test_validate_model_name_invalid(self, model_manager):
        with pytest.raises(ModelNotFoundError):
            model_manager.validate_model_name("large")


class TestIsModelCached:
    def test_is_model_cached_true(self, cached_model_manager):
        assert cached_model_manager.is_model_cached("tiny")

    def test_is_model_cached_false(self, model_manager):
        assert not model_manager.is_model_cached("tiny")

    def test_is_model_cached_empty_dir(self, model_manager):
        model_path = model_manager.get_model_path("tiny")
        model_path.mkdir(parents=True)
        assert not model_manager.is_model_cached("tiny")


class TestRemoveModel:
    def test_remove_model(self, cached_model_manager):
        assert cached_model_manager.is_model_cached("tiny")
        cached_model_manager.remove_model("tiny")
        assert not cached_model_manager.is_model_cached("tiny")

    def test_remove_nonexistent_model(self, model_manager):
        model_manager.remove_model("tiny")


class TestVerifyModel:
    def test_verify_model(self, cached_model_manager):
        assert cached_model_manager.verify_model("tiny")

    def test_verify_model_not_cached(self, model_manager):
        assert not model_manager.verify_model("tiny")

    def test_verify_corrupted_model(self, model_manager):
        model_path = model_manager.get_model_path("tiny")
        model_path.mkdir(parents=True)
        (model_path / "model.bin").write_bytes(b"\x00" * 100)
        assert not model_manager.verify_model("tiny")


class TestClearCache:
    def test_clear_cache(self, cached_model_manager):
        assert cached_model_manager.is_model_cached("tiny")
        cached_model_manager.clear_cache()
        assert not cached_model_manager.is_model_cached("tiny")
        assert not cached_model_manager.get_model_path("tiny").exists()


class TestCacheSize:
    def test_get_cache_size(self, cached_model_manager):
        size = cached_model_manager.get_cache_size()
        assert size == 80_000_000

    def test_get_cache_size_empty(self, model_manager):
        assert model_manager.get_cache_size() == 0


class TestCacheDir:
    def test_cache_dir_property(self, model_manager, tmp_path):
        assert model_manager.cache_dir == tmp_path / "models"

    def test_default_cache_dir(self):
        manager = ModelManager()
        assert manager.cache_dir == Path.home() / ".voice-dictation" / "models"
