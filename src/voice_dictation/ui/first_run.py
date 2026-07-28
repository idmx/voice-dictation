"""First-run setup wizard."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from voice_dictation.config.defaults import CONFIG_DIR, MODELS_DIR
from voice_dictation.config.manager import ConfigManager
from voice_dictation.config.schema import AppConfig
from voice_dictation.platform.permissions import check_all_permissions, check_microphone
from voice_dictation.recognition.model_manager import ModelManager


class FirstRunWizard:
    """Guides the user through first-run setup: config, permissions, model, mic."""

    def __init__(
        self,
        config_manager: ConfigManager | None = None,
        model_manager: ModelManager | None = None,
        config_dir: str | None = None,
    ) -> None:
        self._config_dir = Path(config_dir or CONFIG_DIR).expanduser()
        self._config_manager = config_manager or ConfigManager(
            config_dir=str(self._config_dir),
        )
        self._model_manager = model_manager or ModelManager(
            cache_dir=str(self._config_dir / MODELS_DIR),
        )

    def is_first_run(self) -> bool:
        """Check if this is the first run (no config file exists)."""
        return not self._config_manager.config_path.exists()

    def run(self, model_size: str = "base") -> bool:
        """Run the first-run wizard. Returns True if setup completed."""
        if not self.is_first_run():
            logger.info("Not first run, skipping setup wizard")
            return True

        logger.info("First run detected, starting setup wizard...")

        try:
            self._create_default_config()
        except Exception as e:
            logger.error(f"Failed to create default config: {e}")
            return False

        permissions = self.check_permissions()
        if not all(permissions.values()):
            missing = [k for k, v in permissions.items() if not v]
            logger.warning(f"Missing permissions: {missing}")
            logger.warning("Please grant the required permissions and restart")

        if not self.download_model(model_size):
            logger.error("Model download failed")
            return False

        if not self.test_microphone():
            logger.warning("Microphone test failed — dictation may not work")

        try:
            self._config_manager.save()
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

        logger.info("First-run setup completed successfully")
        return True

    def check_permissions(self) -> dict[str, bool]:
        """Check all required permissions."""
        return check_all_permissions()

    def download_model(self, model_size: str = "base") -> bool:
        """Download the Whisper model."""
        try:
            path = self._model_manager.download_model(model_size)
            logger.info(f"Model downloaded to {path}")
            return True
        except Exception as e:
            logger.error(f"Model download failed: {e}")
            return False

    def test_microphone(self) -> bool:
        """Test that microphone is working."""
        return check_microphone()

    def _create_default_config(self) -> None:
        """Create config with defaults."""
        config = AppConfig()
        self._config_manager.save(config)
        logger.info("Default configuration created")
