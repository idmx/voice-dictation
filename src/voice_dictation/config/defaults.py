"""Default configuration values."""

from voice_dictation.config.schema import AppConfig, _default_hotkey

DEFAULT_CONFIG = AppConfig(hotkey=_default_hotkey())
CONFIG_DIR = "~/.voice-dictation"
CONFIG_FILE = "config.toml"
MODELS_DIR = "models"
LOGS_DIR = "logs"
