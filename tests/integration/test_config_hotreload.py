"""Integration tests for config hot-reload functionality."""

import time
from pathlib import Path

from voice_dictation.config.manager import ConfigManager
from voice_dictation.config.schema import AppConfig


class TestHotkeyChangeApplied:
    """Change hotkey in config file -> ConfigManager notifies subscribers."""

    def test_hotkey_change_applied(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        manager = ConfigManager(config_dir=str(config_dir))
        manager.save()

        received: list[tuple[AppConfig, AppConfig]] = []
        manager.on_reload(lambda old, new: received.append((old, new)))

        manager.start_watching(poll_interval=0.2)
        try:
            config_file = config_dir / "config.toml"
            config_file.write_text(
                'hotkey = "ctrl+alt+f1"\n'
                'language = "ru"\n'
                'whisper_model = "base"\n'
                'mode = "push_to_talk"\n'
                'device = "cpu"\n'
                'compute_type = "int8"\n'
                'injection_method = "clipboard"\n'
                "sound_indicators = true\n"
                "restore_clipboard = true\n"
                'initial_prompt = ""\n'
                "auto_punctuation = true\n"
                'model_cache_dir = "~/.voice-dictation/models"\n'
                'log_level = "INFO"\n',
                encoding="utf-8",
            )

            deadline = time.monotonic() + 3.0
            while not received and time.monotonic() < deadline:
                time.sleep(0.1)

            assert len(received) >= 1
            old_cfg, new_cfg = received[0]
            assert old_cfg.hotkey == "cmd+shift+d"
            assert new_cfg.hotkey == "ctrl+alt+f1"
        finally:
            manager.stop_watching()


class TestModelChangeTriggersReload:
    """Change whisper_model -> event fired."""

    def test_model_change_triggers_reload(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        manager = ConfigManager(config_dir=str(config_dir))
        manager.save()

        received: list[tuple[AppConfig, AppConfig]] = []
        manager.on_reload(lambda old, new: received.append((old, new)))

        manager.start_watching(poll_interval=0.2)
        try:
            config_file = config_dir / "config.toml"
            config_file.write_text(
                'hotkey = "cmd+shift+d"\n'
                'language = "ru"\n'
                'whisper_model = "small"\n'
                'mode = "push_to_talk"\n'
                'device = "cpu"\n'
                'compute_type = "int8"\n'
                'injection_method = "clipboard"\n'
                "sound_indicators = true\n"
                "restore_clipboard = true\n"
                'initial_prompt = ""\n'
                "auto_punctuation = true\n"
                'model_cache_dir = "~/.voice-dictation/models"\n'
                'log_level = "INFO"\n',
                encoding="utf-8",
            )

            deadline = time.monotonic() + 3.0
            while not received and time.monotonic() < deadline:
                time.sleep(0.1)

            assert len(received) >= 1
            _, new_cfg = received[0]
            assert new_cfg.whisper_model == "small"
        finally:
            manager.stop_watching()


class TestLanguageChangeApplied:
    """Change language -> event fired."""

    def test_language_change_applied(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        manager = ConfigManager(config_dir=str(config_dir))
        manager.save()

        received: list[tuple[AppConfig, AppConfig]] = []
        manager.on_reload(lambda old, new: received.append((old, new)))

        manager.start_watching(poll_interval=0.2)
        try:
            config_file = config_dir / "config.toml"
            config_file.write_text(
                'hotkey = "cmd+shift+d"\n'
                'language = "de"\n'
                'whisper_model = "base"\n'
                'mode = "push_to_talk"\n'
                'device = "cpu"\n'
                'compute_type = "int8"\n'
                'injection_method = "clipboard"\n'
                "sound_indicators = true\n"
                "restore_clipboard = true\n"
                'initial_prompt = ""\n'
                "auto_punctuation = true\n"
                'model_cache_dir = "~/.voice-dictation/models"\n'
                'log_level = "INFO"\n',
                encoding="utf-8",
            )

            deadline = time.monotonic() + 3.0
            while not received and time.monotonic() < deadline:
                time.sleep(0.1)

            assert len(received) >= 1
            _, new_cfg = received[0]
            assert new_cfg.language == "de"
        finally:
            manager.stop_watching()


class TestSoundToggleApplied:
    """Change sound_indicators -> event fired."""

    def test_sound_toggle_applied(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        manager = ConfigManager(config_dir=str(config_dir))
        manager.save()

        received: list[tuple[AppConfig, AppConfig]] = []
        manager.on_reload(lambda old, new: received.append((old, new)))

        manager.start_watching(poll_interval=0.2)
        try:
            config_file = config_dir / "config.toml"
            config_file.write_text(
                'hotkey = "cmd+shift+d"\n'
                'language = "ru"\n'
                'whisper_model = "base"\n'
                'mode = "push_to_talk"\n'
                'device = "cpu"\n'
                'compute_type = "int8"\n'
                'injection_method = "clipboard"\n'
                "sound_indicators = false\n"
                "restore_clipboard = true\n"
                'initial_prompt = ""\n'
                "auto_punctuation = true\n"
                'model_cache_dir = "~/.voice-dictation/models"\n'
                'log_level = "INFO"\n',
                encoding="utf-8",
            )

            deadline = time.monotonic() + 3.0
            while not received and time.monotonic() < deadline:
                time.sleep(0.1)

            assert len(received) >= 1
            _, new_cfg = received[0]
            assert new_cfg.sound_indicators is False
        finally:
            manager.stop_watching()


class TestInvalidConfigNotApplied:
    """Write invalid config -> old config retained, error logged."""

    def test_invalid_config_not_applied(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        manager = ConfigManager(config_dir=str(config_dir))
        manager.save()
        original_hotkey = manager.config.hotkey

        received: list[tuple[AppConfig, AppConfig]] = []
        manager.on_reload(lambda old, new: received.append((old, new)))

        manager.start_watching(poll_interval=0.2)
        try:
            config_file = config_dir / "config.toml"
            config_file.write_text(
                'hotkey = ""\n',
                encoding="utf-8",
            )

            deadline = time.monotonic() + 3.0
            while not received and time.monotonic() < deadline:
                time.sleep(0.1)

            assert manager.config.hotkey == original_hotkey
        finally:
            manager.stop_watching()


class TestConfigFileCreationOnFirstRun:
    """No config file -> defaults written."""

    def test_config_file_creation_on_first_run(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        assert not config_file.exists()

        manager = ConfigManager(config_dir=str(config_dir))
        manager.save()

        assert config_file.exists()
        content = config_file.read_text(encoding="utf-8")
        assert "hotkey" in content


class TestConfigMigrationAddsNewFields:
    """Old config missing fields -> migrated with defaults."""

    def test_config_migration_adds_new_fields(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"

        config_file.write_text(
            'hotkey = "alt+f1"\n',
            encoding="utf-8",
        )

        manager = ConfigManager(config_dir=str(config_dir))
        config = manager.load()

        assert config.hotkey == "alt+f1"
        assert config.language == "ru"
        assert config.whisper_model == "base"
        assert config.mode == "push_to_talk"
        assert config.sound_indicators is True
        assert config.auto_punctuation is True
        assert config.restore_clipboard is True
