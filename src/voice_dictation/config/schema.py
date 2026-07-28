"""Configuration schema using Pydantic v2."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from voice_dictation.platform.detect import is_macos


def _default_hotkey() -> str:
    """Return platform-appropriate default hotkey."""
    if is_macos():
        return "cmd+shift+1"
    return "ctrl+shift+1"


class AppConfig(BaseModel):
    """Application configuration schema."""

    hotkey: str = Field(default_factory=_default_hotkey, description="Global hotkey combination")
    mode: Literal["push_to_talk", "toggle"] = Field(
        default="push_to_talk", description="Hotkey activation mode"
    )
    whisper_model: Literal["tiny", "base", "small", "medium"] = Field(
        default="base", description="Whisper model size"
    )
    language: str = Field(default="ru", description="Recognition language code")
    device: Literal["cpu", "cuda"] = Field(default="cpu", description="Compute device")
    compute_type: Literal["int8", "float16", "float32"] = Field(
        default="int8", description="Computation precision"
    )
    injection_method: Literal["clipboard", "typing"] = Field(
        default="clipboard", description="Text injection method"
    )
    audio_device: int | None = Field(default=None, description="Audio device index (None=default)")
    sound_indicators: bool = Field(default=True, description="Play sound indicators")
    restore_clipboard: bool = Field(default=True, description="Restore clipboard after injection")
    initial_prompt: str = Field(
        default="Текст на русском языке.",
        description="Initial prompt for Whisper context — improves recognition accuracy and punctuation",
    )
    auto_punctuation: bool = Field(default=True, description="Enable automatic punctuation")
    beam_size: Literal[1, 3, 5] = Field(
        default=5, description="Beam size: 1=fast, 3=balanced, 5=accurate"
    )
    model_cache_dir: str = Field(
        default="~/.voice-dictation/models", description="Model cache directory"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    @field_validator("hotkey")
    @classmethod
    def validate_hotkey(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Hotkey cannot be empty")
        return v.strip().lower()

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("Language code must be at least 2 characters")
        return v.lower()

    @field_validator("model_cache_dir")
    @classmethod
    def validate_model_cache_dir(cls, v: str) -> str:
        from pathlib import Path

        expanded = Path(v).expanduser().resolve()
        allowed = Path.home() / ".voice-dictation"
        if not str(expanded).startswith(str(allowed.resolve())):
            raise ValueError(
                f"model_cache_dir must be under ~/.voice-dictation/, got '{v}'"
            )
        return v

    model_config = {"extra": "ignore"}
