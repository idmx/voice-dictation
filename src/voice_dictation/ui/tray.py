"""System tray icon controller for Voice Dictation."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from PIL import Image

from voice_dictation.config.schema import AppConfig
from voice_dictation.core.state import State

if TYPE_CHECKING:
    import pystray

    from voice_dictation.app import Application

ICONS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "icons"

_STATE_ICON_MAP: dict[State, str] = {
    State.IDLE: "idle",
    State.RECORDING: "recording",
    State.TRANSCRIBING: "processing",
    State.INJECTING: "processing",
}

_STATE_TOOLTIP_MAP: dict[State, str] = {
    State.IDLE: "Готов",
    State.RECORDING: "Запись...",
    State.TRANSCRIBING: "Обработка...",
    State.INJECTING: "Вставка...",
}

_AVAILABLE_MODELS = ("tiny", "base", "small")
_AVAILABLE_LANGUAGES = ("ru", "en")
_AVAILABLE_MODES = ("push_to_talk", "toggle")


class TrayIcon:
    """System tray icon controller for Voice Dictation."""

    def __init__(self, config: AppConfig, app: Application | None = None) -> None:
        self._config = config
        self._app = app
        self._icon: pystray.Icon | None = None
        self._current_state = State.IDLE
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the tray icon in a background thread."""
        try:
            import pystray
        except ImportError:
            logger.warning("pystray not available, tray icon disabled")
            return

        initial_image = self._load_icon("idle")
        menu = self._create_menu()

        self._icon = pystray.Icon(
            name="Voice Dictation",
            icon=initial_image,
            title="Voice Dictation — Готов",
            menu=menu,
        )

        self._thread = threading.Thread(
            target=self._icon.run,
            daemon=True,
            name="tray-icon",
        )
        self._thread.start()
        logger.info("Tray icon started")

    def stop(self) -> None:
        """Stop the tray icon."""
        if self._icon is None:
            return
        try:
            self._icon.stop()
        except Exception as exc:
            logger.debug(f"Error stopping tray icon: {exc}")
        self._icon = None
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("Tray icon stopped")

    def update_icon(self, state: State) -> None:
        """Update tray icon and tooltip based on state."""
        if self._icon is None:
            return
        self._current_state = state
        icon_name = _STATE_ICON_MAP.get(state, "idle")
        tooltip_suffix = _STATE_TOOLTIP_MAP.get(state, "Готов")
        try:
            image = self._load_icon(icon_name)
            self._icon.icon = image
            self._icon.title = f"Voice Dictation — {tooltip_suffix}"
            self._icon.update_menu()
        except Exception as exc:
            logger.debug(f"Failed to update tray icon: {exc}")

    def _load_icon(self, name: str) -> Image.Image:
        """Load an icon image from assets/icons/."""
        for suffix in (".png", "_circle.png"):
            path = ICONS_DIR / f"{name}{suffix}"
            if path.exists():
                try:
                    return Image.open(path)
                except Exception as exc:
                    logger.debug(f"Failed to load icon {path}: {exc}")

        pkg_icons = Path(__file__).resolve().parent / "icons"
        for suffix in (".png", "_circle.png"):
            path = pkg_icons / f"{name}{suffix}"
            if path.exists():
                try:
                    return Image.open(path)
                except Exception as exc:
                    logger.debug(f"Failed to load icon {path}: {exc}")

        return self._generate_fallback_icon(name)

    @staticmethod
    def _generate_fallback_icon(name: str) -> Image.Image:
        """Generate a simple coloured circle when icon files are missing."""
        color_map: dict[str, tuple[int, int, int]] = {
            "idle": (100, 100, 100),
            "recording": (220, 50, 50),
            "processing": (50, 120, 220),
        }
        color = color_map.get(name, (100, 100, 100))
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        draw.ellipse((4, 4, size - 4, size - 4), fill=color)
        return img

    def _create_menu(self) -> pystray.Menu:
        """Create the tray context menu."""
        import pystray

        status_text = _STATE_TOOLTIP_MAP.get(self._current_state, "Готов")

        return pystray.Menu(
            pystray.MenuItem(
                f"● {status_text}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Модель",
                pystray.Menu(
                    *(
                        pystray.MenuItem(
                            m,
                            lambda _, m=m: self._on_model_change(m),
                            checked=lambda _, m=m: self._config.whisper_model == m,
                            radio=True,
                        )
                        for m in _AVAILABLE_MODELS
                    )
                ),
            ),
            pystray.MenuItem(
                "Язык",
                pystray.Menu(
                    *(
                        pystray.MenuItem(
                            lang,
                            lambda _, lng=lang: self._on_language_change(lng),
                            checked=lambda _, lng=lang: self._config.language == lng,
                            radio=True,
                        )
                        for lang in _AVAILABLE_LANGUAGES
                    )
                ),
            ),
            pystray.MenuItem(
                "Режим",
                pystray.Menu(
                    *(
                        pystray.MenuItem(
                            mode,
                            lambda _, m=mode: self._on_mode_change(m),
                            checked=lambda _, m=mode: self._config.mode == m,
                            radio=True,
                        )
                        for mode in _AVAILABLE_MODES
                    )
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Настройки...", self._on_open_settings),
            pystray.MenuItem("Перезапуск", self._on_restart),
            pystray.MenuItem("Выход", self._on_quit),
        )

    def _on_quit(self) -> None:
        """Handle quit menu click."""
        if self._app:
            self._app.shutdown()

    def _on_restart(self) -> None:
        """Handle restart menu click."""
        if self._app and self._app.pipeline:
            self._app.pipeline.stop()
            try:
                self._app._init_components()
                if self._app.pipeline:
                    self._app.pipeline.start()
                logger.info("Application restarted via tray")
            except Exception as exc:
                logger.error(f"Failed to restart application: {exc}")

    def _on_open_settings(self) -> None:
        """Open config file in default editor."""
        from voice_dictation.config.defaults import CONFIG_DIR, CONFIG_FILE

        config_path = Path(CONFIG_DIR).expanduser() / CONFIG_FILE
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if not config_path.exists():
            try:
                from voice_dictation.config.manager import ConfigManager

                mgr = ConfigManager(config_dir=str(config_path.parent))
                mgr.save()
            except Exception as exc:
                logger.error(f"Failed to create default config: {exc}")

        try:
            import sys

            if sys.platform == "darwin":
                subprocess.Popen(["open", str(config_path)])
            elif sys.platform == "win32":
                subprocess.Popen(["start", str(config_path)], shell=True)
            else:
                subprocess.Popen(["xdg-open", str(config_path)])
        except Exception as exc:
            logger.error(f"Failed to open settings: {exc}")

    def _on_model_change(self, model: str) -> None:
        """Handle model menu change."""
        try:
            self._config = self._config.model_copy(update={"whisper_model": model})
            if self._app:
                self._app._config = self._config
                if self._app._recognition_engine:
                    self._app._recognition_engine.reload(model)
            logger.info(f"Model changed to '{model}'")
        except Exception as exc:
            logger.error(f"Failed to change model: {exc}")

    def _on_language_change(self, lang: str) -> None:
        """Handle language menu change."""
        try:
            self._config = self._config.model_copy(update={"language": lang})
            if self._app:
                self._app._config = self._config
            logger.info(f"Language changed to '{lang}'")
        except Exception as exc:
            logger.error(f"Failed to change language: {exc}")

    def _on_mode_change(self, mode: str) -> None:
        """Handle mode menu change."""
        try:
            self._config = self._config.model_copy(update={"mode": mode})
            if self._app:
                self._app._config = self._config
                if self._app._hotkey_listener:
                    logger.info(f"Mode changed to '{mode}' — hotkey listener may need restart")
            logger.info(f"Mode changed to '{mode}'")
        except Exception as exc:
            logger.error(f"Failed to change mode: {exc}")
