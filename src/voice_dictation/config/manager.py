"""Configuration manager — load, save, and hot-reload TOML config."""

import sys
import threading
from pathlib import Path

from loguru import logger

from voice_dictation.config.defaults import CONFIG_DIR, CONFIG_FILE, DEFAULT_CONFIG
from voice_dictation.config.schema import AppConfig
from voice_dictation.core.exceptions import ConfigError

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


def _toml_dumps(data: dict, indent: int = 0) -> str:
    """Simple TOML serializer for AppConfig dict output."""
    lines: list[str] = []
    prefix = "  " * indent
    for key, value in data.items():
        if isinstance(value, bool):
            lines.append(f"{prefix}{key} = {str(value).lower()}")
        elif isinstance(value, (int, float)):
            lines.append(f"{prefix}{key} = {value}")
        elif isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{prefix}{key} = "{escaped}"')
        elif isinstance(value, dict):
            lines.append(f"{prefix}[{key}]")
            lines.append(_toml_dumps(value, indent + 1))
        elif value is None:
            lines.append(f"{prefix}# {key} = null")
    return "\n".join(lines)


class ConfigManager:
    """Manages loading, saving, and watching the TOML configuration file."""

    def __init__(
        self,
        config_dir: str | None = None,
        config_file: str | None = None,
    ) -> None:
        self._config_dir = Path(config_dir or CONFIG_DIR).expanduser()
        self._config_file = self._config_dir / (config_file or CONFIG_FILE)
        self._config: AppConfig = DEFAULT_CONFIG.model_copy()
        self._watcher_thread: threading.Thread | None = None
        self._watcher_stop = threading.Event()
        self._on_reload_callbacks: list = []

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def config_path(self) -> Path:
        return self._config_file

    def load(self) -> AppConfig:
        """Load configuration from TOML file, falling back to defaults."""
        if not self._config_file.exists():
            logger.info(f"Config file not found at {self._config_file}, using defaults")
            self._config = DEFAULT_CONFIG.model_copy()
            return self._config

        if tomllib is None:
            logger.warning("No TOML parser available, using defaults")
            self._config = DEFAULT_CONFIG.model_copy()
            return self._config

        try:
            raw = self._config_file.read_text(encoding="utf-8")
            data = tomllib.loads(raw)
            merged = self._merge_with_defaults(data)
            self._config = AppConfig(**merged)
            logger.info(f"Configuration loaded from {self._config_file}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}, using defaults")
            self._config = DEFAULT_CONFIG.model_copy()

        return self._config

    def save(self, config: AppConfig | None = None) -> None:
        """Save configuration to TOML file."""
        target = config or self._config
        self._config_dir.mkdir(parents=True, exist_ok=True)

        try:
            data = target.model_dump()
            toml_str = _toml_dumps(data)
            self._config_file.write_text(toml_str + "\n", encoding="utf-8")
            if config is not None:
                self._config = config
            logger.info(f"Configuration saved to {self._config_file}")
        except Exception as e:
            raise ConfigError(f"Failed to save config: {e}") from e

    def _merge_with_defaults(self, data: dict) -> dict:
        """Merge user data with defaults, adding any missing fields."""
        defaults = DEFAULT_CONFIG.model_dump()
        merged = {**defaults, **data}
        return merged

    def start_watching(self, poll_interval: float = 2.0) -> None:
        """Start watching the config file for changes (hot-reload)."""
        if self._watcher_thread and self._watcher_thread.is_alive():
            return

        self._watcher_stop.clear()
        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            args=(poll_interval,),
            daemon=True,
            name="config-watcher",
        )
        self._watcher_thread.start()
        logger.info("Config file watcher started")

    def stop_watching(self) -> None:
        """Stop watching the config file."""
        self._watcher_stop.set()
        if self._watcher_thread and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=5)
        logger.info("Config file watcher stopped")

    def on_reload(self, callback) -> None:
        """Register a callback to be called when config is reloaded."""
        self._on_reload_callbacks.append(callback)

    def _watch_loop(self, poll_interval: float) -> None:
        """Poll the config file for changes."""
        last_mtime: float = 0
        if self._config_file.exists():
            last_mtime = self._config_file.stat().st_mtime

        while not self._watcher_stop.wait(poll_interval):
            try:
                if not self._config_file.exists():
                    continue
                current_mtime = self._config_file.stat().st_mtime
                if current_mtime > last_mtime:
                    last_mtime = current_mtime
                    logger.info("Config file changed, reloading...")
                    old_config = self._config
                    self.load()
                    for cb in self._on_reload_callbacks:
                        try:
                            cb(old_config, self._config)
                        except Exception as e:
                            logger.error(f"Config reload callback error: {e}")
            except Exception as e:
                logger.error(f"Config watcher error: {e}")
