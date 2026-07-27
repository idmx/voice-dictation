"""Unit tests for the config manager."""

from pathlib import Path

from voice_dictation.config.manager import ConfigManager
from voice_dictation.config.schema import AppConfig


class TestConfigManager:
    """Tests for the ConfigManager."""

    def test_load_missing_file_returns_defaults(self, tmp_config_manager: ConfigManager) -> None:
        config = tmp_config_manager.load()
        assert config.hotkey == "cmd+shift+d"
        assert config.language == "ru"
        assert config.whisper_model == "base"

    def test_load_valid_config(self, tmp_config_dir: Path) -> None:
        config_file = tmp_config_dir / "config.toml"
        config_file.write_text(
            'hotkey = "ctrl+shift+v"\n'
            'language = "en"\n'
            'whisper_model = "small"\n'
            'log_level = "DEBUG"\n',
            encoding="utf-8",
        )
        manager = ConfigManager(config_dir=str(tmp_config_dir))
        config = manager.load()
        assert config.hotkey == "ctrl+shift+v"
        assert config.language == "en"
        assert config.whisper_model == "small"
        assert config.log_level == "DEBUG"

    def test_load_corrupted_toml_returns_defaults(self, tmp_config_dir: Path) -> None:
        config_file = tmp_config_dir / "config.toml"
        config_file.write_text("this is = not = valid toml [[", encoding="utf-8")
        manager = ConfigManager(config_dir=str(tmp_config_dir))
        config = manager.load()
        assert config.hotkey == "cmd+shift+d"
        assert config.language == "ru"

    def test_load_missing_fields_merges_defaults(self, tmp_config_dir: Path) -> None:
        config_file = tmp_config_dir / "config.toml"
        config_file.write_text(
            'hotkey = "alt+f1"\n',
            encoding="utf-8",
        )
        manager = ConfigManager(config_dir=str(tmp_config_dir))
        config = manager.load()
        assert config.hotkey == "alt+f1"
        assert config.language == "ru"
        assert config.whisper_model == "base"
        assert config.mode == "push_to_talk"

    def test_save_creates_file(self, tmp_config_dir: Path) -> None:
        manager = ConfigManager(config_dir=str(tmp_config_dir))
        config = AppConfig(hotkey="alt+f2", language="fr")
        manager.save(config)
        config_path = tmp_config_dir / "config.toml"
        assert config_path.exists()

        manager2 = ConfigManager(config_dir=str(tmp_config_dir))
        loaded = manager2.load()
        assert loaded.hotkey == "alt+f2"
        assert loaded.language == "fr"

    def test_save_creates_config_dir(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "nested" / "config"
        manager = ConfigManager(config_dir=str(config_dir))
        manager.save()
        assert config_dir.exists()
        assert (config_dir / "config.toml").exists()

    def test_config_path_property(self, tmp_config_dir: Path) -> None:
        manager = ConfigManager(config_dir=str(tmp_config_dir))
        assert manager.config_path == tmp_config_dir / "config.toml"

    def test_config_property_after_load(self, tmp_config_manager: ConfigManager) -> None:
        tmp_config_manager.load()
        assert tmp_config_manager.config.hotkey == "cmd+shift+d"

    def test_invalid_hotkey_in_file_returns_defaults(self, tmp_config_dir: Path) -> None:
        config_file = tmp_config_dir / "config.toml"
        config_file.write_text(
            'hotkey = ""\n',
            encoding="utf-8",
        )
        manager = ConfigManager(config_dir=str(tmp_config_dir))
        config = manager.load()
        assert config.hotkey == "cmd+shift+d"

    def test_load_from_fixture_valid(self, config_samples_dir: Path, tmp_config_dir: Path) -> None:
        valid_path = config_samples_dir / "valid.toml"
        shutil_content = valid_path.read_text(encoding="utf-8")
        config_file = tmp_config_dir / "config.toml"
        config_file.write_text(shutil_content, encoding="utf-8")

        manager = ConfigManager(config_dir=str(tmp_config_dir))
        config = manager.load()
        assert config.hotkey == "alt+shift+d"
        assert config.language == "en"
        assert config.whisper_model == "small"
        assert config.mode == "toggle"

    def test_load_from_fixture_missing_fields(
        self, config_samples_dir: Path, tmp_config_dir: Path
    ) -> None:
        missing_path = config_samples_dir / "missing_fields.toml"
        content = missing_path.read_text(encoding="utf-8")
        config_file = tmp_config_dir / "config.toml"
        config_file.write_text(content, encoding="utf-8")

        manager = ConfigManager(config_dir=str(tmp_config_dir))
        config = manager.load()
        assert config.hotkey == "ctrl+f1"
        assert config.language == "ru"
        assert config.whisper_model == "base"

    def test_load_from_fixture_invalid_hotkey(
        self, config_samples_dir: Path, tmp_config_dir: Path
    ) -> None:
        invalid_path = config_samples_dir / "invalid_hotkey.toml"
        content = invalid_path.read_text(encoding="utf-8")
        config_file = tmp_config_dir / "config.toml"
        config_file.write_text(content, encoding="utf-8")

        manager = ConfigManager(config_dir=str(tmp_config_dir))
        config = manager.load()
        assert config.hotkey == "cmd+shift+d"

    def test_save_then_reload_preserves_all_fields(self, tmp_config_dir: Path) -> None:
        manager = ConfigManager(config_dir=str(tmp_config_dir))
        original = AppConfig(
            hotkey="win+space",
            mode="toggle",
            whisper_model="tiny",
            language="de",
            device="cpu",
            compute_type="float32",
            injection_method="typing",
            audio_device=3,
            sound_indicators=False,
            restore_clipboard=False,
            initial_prompt="Custom prompt",
            auto_punctuation=False,
            log_level="WARNING",
        )
        manager.save(original)

        manager2 = ConfigManager(config_dir=str(tmp_config_dir))
        loaded = manager2.load()
        assert loaded == original

    def test_config_manager_uses_expanded_user_path(self) -> None:
        manager = ConfigManager(config_dir="~/.voice-dictation-test")
        assert "~" not in str(manager.config_path)
