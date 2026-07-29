"""Unit tests for the config schema."""

import pytest
from pydantic import ValidationError

from voice_dictation.config.schema import AppConfig, _default_hotkey


class TestAppConfig:
    """Tests for the AppConfig schema."""

    def test_default_config(self, default_config: AppConfig) -> None:
        assert default_config.hotkey == _default_hotkey()
        assert default_config.mode == "push_to_talk"
        assert default_config.whisper_model == "base"
        assert default_config.language == "ru"
        assert default_config.device == "cpu"
        assert default_config.compute_type == "int8"
        assert default_config.injection_method == "clipboard"
        assert default_config.audio_device is None
        assert default_config.sound_indicators is True
        assert default_config.restore_clipboard is True
        assert default_config.initial_prompt == "Текст на русском языке."
        assert default_config.auto_punctuation is True
        assert default_config.model_cache_dir == "~/.voice-dictation/models"
        assert default_config.log_level == "INFO"

    def test_custom_config(self, sample_config: AppConfig) -> None:
        assert sample_config.hotkey == "ctrl+shift+v"
        assert sample_config.mode == "toggle"
        assert sample_config.whisper_model == "small"
        assert sample_config.language == "en"
        assert sample_config.device == "cpu"
        assert sample_config.compute_type == "float16"
        assert sample_config.injection_method == "typing"
        assert sample_config.audio_device == 0
        assert sample_config.sound_indicators is False
        assert sample_config.restore_clipboard is False
        assert sample_config.initial_prompt == "Test prompt"
        assert sample_config.auto_punctuation is False
        assert sample_config.log_level == "DEBUG"

    def test_hotkey_normalized_to_lower(self) -> None:
        config = AppConfig(hotkey="CMD+SHIFT+1")
        assert config.hotkey == "cmd+shift+1"

    def test_hotkey_stripped(self) -> None:
        config = AppConfig(hotkey="  cmd+shift+1  ")
        assert config.hotkey == "cmd+shift+1"

    def test_empty_hotkey_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(hotkey="")
        assert "Hotkey cannot be empty" in str(exc_info.value)

    def test_whitespace_hotkey_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(hotkey="   ")
        assert "Hotkey cannot be empty" in str(exc_info.value)

    def test_language_normalized_to_lower(self) -> None:
        config = AppConfig(language="EN")
        assert config.language == "en"

    def test_short_language_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(language="e")
        assert "at least 2 characters" in str(exc_info.value)

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(mode="invalid")

    def test_invalid_whisper_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(whisper_model="huge")

    def test_invalid_device_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(device="tpu")

    def test_invalid_compute_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(compute_type="int4")

    def test_invalid_injection_method_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(injection_method="paste")

    def test_invalid_log_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AppConfig(log_level="TRACE")

    def test_audio_device_none_allowed(self) -> None:
        config = AppConfig(audio_device=None)
        assert config.audio_device is None

    def test_audio_device_int_allowed(self) -> None:
        config = AppConfig(audio_device=2)
        assert config.audio_device == 2

    def test_extra_fields_ignored(self) -> None:
        config = AppConfig(nonexistent_field="value")  # type: ignore
        assert not hasattr(config, "nonexistent_field")

    def test_model_dump_roundtrip(self, sample_config: AppConfig) -> None:
        data = sample_config.model_dump()
        restored = AppConfig(**data)
        assert restored == sample_config

    def test_model_copy(self, default_config: AppConfig) -> None:
        copied = default_config.model_copy(update={"language": "en"})
        assert copied.language == "en"
        assert default_config.language == "ru"
