"""Default configuration values."""

import sys

from voice_dictation.config.schema import AppConfig

# Platform-specific default hotkey
_DEFAULT_HOTKEY = "cmd+shift+1" if sys.platform == "darwin" else "win+shift+1"

DEFAULT_CONFIG = AppConfig(hotkey=_DEFAULT_HOTKEY)
CONFIG_DIR = "~/.voice-dictation"
CONFIG_FILE = "config.toml"
MODELS_DIR = "models"
LOGS_DIR = "logs"
