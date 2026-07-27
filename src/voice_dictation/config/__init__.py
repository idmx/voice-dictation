"""Configuration module."""

from voice_dictation.config.defaults import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULT_CONFIG,
    LOGS_DIR,
    MODELS_DIR,
)
from voice_dictation.config.manager import ConfigManager
from voice_dictation.config.schema import AppConfig

__all__ = [
    "AppConfig",
    "ConfigManager",
    "DEFAULT_CONFIG",
    "CONFIG_DIR",
    "CONFIG_FILE",
    "MODELS_DIR",
    "LOGS_DIR",
]
