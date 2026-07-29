"""Tests for the first-run setup wizard."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voice_dictation.config.manager import ConfigManager
from voice_dictation.ui.first_run import FirstRunWizard

ALL_GRANTED = {"accessibility": True, "microphone": True}


@pytest.fixture
def mock_config_manager(tmp_config_dir: Path) -> MagicMock:
    """Provide a mocked ConfigManager backed by a temp directory."""
    cm = ConfigManager(config_dir=str(tmp_config_dir))
    mock = MagicMock(wraps=cm)
    mock.config_path = cm.config_path
    return mock


@pytest.fixture
def mock_model_manager() -> MagicMock:
    """Provide a mocked ModelManager."""
    mock = MagicMock()
    mock.download_model.return_value = Path("/fake/models/model-base")
    return mock


@pytest.fixture
def wizard(mock_config_manager: MagicMock, mock_model_manager: MagicMock) -> FirstRunWizard:
    """Provide a FirstRunWizard with mocked dependencies."""
    return FirstRunWizard(
        config_manager=mock_config_manager,
        model_manager=mock_model_manager,
        config_dir=str(mock_config_manager.config_path.parent),
    )


class TestIsFirstRun:
    def test_is_first_run_no_config(self, wizard: FirstRunWizard) -> None:
        assert wizard.is_first_run() is True

    def test_is_first_run_with_config(
        self, wizard: FirstRunWizard, mock_config_manager: MagicMock
    ) -> None:
        mock_config_manager.save()
        assert wizard.is_first_run() is False


class TestRun:
    def test_run_creates_config(
        self,
        wizard: FirstRunWizard,
        mock_config_manager: MagicMock,
        mock_model_manager: MagicMock,
    ) -> None:
        with (
            patch.object(wizard, "check_permissions", return_value=ALL_GRANTED),
            patch.object(wizard, "test_microphone", return_value=True),
        ):
            result = wizard.run()

        assert result is True
        mock_config_manager.save.assert_called()

    def test_run_downloads_model(
        self,
        wizard: FirstRunWizard,
        mock_model_manager: MagicMock,
    ) -> None:
        with (
            patch.object(wizard, "check_permissions", return_value=ALL_GRANTED),
            patch.object(wizard, "test_microphone", return_value=True),
        ):
            wizard.run()

        mock_model_manager.download_model.assert_called_once_with("base")

    def test_run_tests_microphone(self, wizard: FirstRunWizard) -> None:
        with (
            patch.object(wizard, "check_permissions", return_value=ALL_GRANTED),
            patch.object(wizard, "download_model", return_value=True),
            patch.object(wizard, "test_microphone", return_value=True) as mock_mic,
        ):
            wizard.run()

        mock_mic.assert_called_once()

    def test_run_skips_when_not_first_run(self, wizard: FirstRunWizard) -> None:
        with patch.object(wizard, "is_first_run", return_value=False):
            result = wizard.run()

        assert result is True

    def test_run_fails_on_model_download_failure(
        self,
        wizard: FirstRunWizard,
        mock_model_manager: MagicMock,
    ) -> None:
        mock_model_manager.download_model.side_effect = RuntimeError("download failed")
        with (
            patch.object(wizard, "check_permissions", return_value=ALL_GRANTED),
            patch.object(wizard, "test_microphone", return_value=True),
        ):
            result = wizard.run()

        assert result is False


class TestCheckPermissions:
    def test_check_permissions_all_granted(self, wizard: FirstRunWizard) -> None:
        with patch(
            "voice_dictation.ui.first_run.check_all_permissions",
            return_value={"accessibility": True, "microphone": True},
        ):
            result = wizard.check_permissions()

        assert result == {"accessibility": True, "microphone": True}

    def test_check_permissions_missing(self, wizard: FirstRunWizard) -> None:
        with patch(
            "voice_dictation.ui.first_run.check_all_permissions",
            return_value={"accessibility": False, "microphone": True},
        ):
            result = wizard.check_permissions()

        assert result["accessibility"] is False
        assert result["microphone"] is True


class TestDownloadModel:
    def test_download_model_success(
        self, wizard: FirstRunWizard, mock_model_manager: MagicMock
    ) -> None:
        result = wizard.download_model("base")

        assert result is True
        mock_model_manager.download_model.assert_called_once_with("base")

    def test_download_model_failure(
        self, wizard: FirstRunWizard, mock_model_manager: MagicMock
    ) -> None:
        mock_model_manager.download_model.side_effect = RuntimeError("network error")
        result = wizard.download_model("base")

        assert result is False


class TestTestMicrophone:
    def test_test_microphone_success(self, wizard: FirstRunWizard) -> None:
        with patch("voice_dictation.ui.first_run.check_microphone", return_value=True):
            result = wizard.test_microphone()

        assert result is True

    def test_test_microphone_failure(self, wizard: FirstRunWizard) -> None:
        with patch("voice_dictation.ui.first_run.check_microphone", return_value=False):
            result = wizard.test_microphone()

        assert result is False
