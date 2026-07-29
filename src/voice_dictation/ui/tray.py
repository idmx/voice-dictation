"""System tray icon controller for Voice Dictation."""

from __future__ import annotations

import os
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

_AVAILABLE_MODELS = ("tiny", "base", "small", "medium")
_AVAILABLE_LANGUAGES = ("ru", "en")
_AVAILABLE_MODES = ("push_to_talk", "toggle")
# beam_size menu: (label, value)
_AVAILABLE_BEAM_SIZES: list[tuple[str, int]] = [
    ("Быстро (1)", 1),
    ("Баланс (3)", 3),
    ("Точно (5)", 5),
]
# max_recording_seconds menu: (label, value)
_AVAILABLE_RECORDING_TIMEOUTS: list[tuple[str, int]] = [
    ("15 сек", 15),
    ("30 сек", 30),
    ("1 мин", 60),
    ("2 мин", 120),
    ("5 мин", 300),
]


class TrayIcon:
    """System tray icon controller for Voice Dictation."""

    def __init__(self, config: AppConfig, app: Application | None = None) -> None:
        self._config = config
        self._app = app
        self._icon: pystray.Icon | None = None
        self._current_state = State.IDLE
        self._thread: threading.Thread | None = None
        self._model_loading = False
        self._loading_status: str | None = None
        self._icon_cache: dict[str, Image.Image] = {}

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

    def run_blocking(self) -> None:
        """Run the tray icon in the **current** (main) thread.

        This is required on macOS so the main thread processes system events.
        The call blocks until :meth:`stop` is invoked.
        """
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
        logger.info("Tray icon starting (main thread)")
        self._icon.run()

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
        # Override with loading state if model is downloading/loading
        if self._model_loading:
            icon_name = "loading"
            tooltip_suffix = self._loading_status or "Загрузка модели..."
        else:
            icon_name = _STATE_ICON_MAP.get(state, "idle")
            tooltip_suffix = _STATE_TOOLTIP_MAP.get(state, "Готов")
        try:
            image = self._load_icon(icon_name)
            self._icon.icon = image
            self._icon.title = f"Voice Dictation — {tooltip_suffix}"
            self._icon.update_menu()
        except Exception as exc:
            logger.debug(f"Failed to update tray icon: {exc}")

    def set_model_loading(self, loading: bool, status: str | None = None) -> None:
        """Show/hide model loading indicator in tray.

        Args:
            loading: Whether the model is currently loading.
            status: Optional status text (e.g. "Загрузка 45%").
        """
        self._model_loading = loading
        self._loading_status = status if loading else None
        self.update_icon(self._current_state)
        # Refresh menu so status line updates
        if self._icon is not None:
            try:
                self._icon.menu = self._create_menu()
                self._icon.update_menu()
            except Exception:
                pass

    def _load_icon(self, name: str) -> Image.Image:
        """Load an icon image, with caching to avoid repeated file I/O."""
        # Return cached icon if available
        if name in self._icon_cache:
            return self._icon_cache[name]

        for suffix in (".png", "_circle.png"):
            path = ICONS_DIR / f"{name}{suffix}"
            if path.exists():
                try:
                    img = Image.open(path)
                    img.load()  # Force-load pixel data so file handle is released
                    self._icon_cache[name] = img
                    return img
                except Exception as exc:
                    logger.debug(f"Failed to load icon {path}: {exc}")

        pkg_icons = Path(__file__).resolve().parent / "icons"
        for suffix in (".png", "_circle.png"):
            path = pkg_icons / f"{name}{suffix}"
            if path.exists():
                try:
                    img = Image.open(path)
                    img.load()  # Force-load pixel data so file handle is released
                    self._icon_cache[name] = img
                    return img
                except Exception as exc:
                    logger.debug(f"Failed to load icon {path}: {exc}")

        img = self._generate_fallback_icon(name)
        self._icon_cache[name] = img
        return img

    @staticmethod
    def _generate_fallback_icon(name: str) -> Image.Image:
        """Generate a simple coloured circle when icon files are missing."""
        color_map: dict[str, tuple[int, int, int]] = {
            "idle": (100, 100, 100),
            "recording": (220, 50, 50),
            "processing": (50, 120, 220),
            "loading": (230, 150, 30),
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

        if self._model_loading and self._loading_status:
            status_text = self._loading_status
        elif self._model_loading:
            status_text = "Загрузка модели..."
        else:
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
                            lambda *_, m=m: self._on_model_change(m),
                            checked=lambda *_, m=m: self._config.whisper_model == m,
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
                            lambda *_, lng=lang: self._on_language_change(lng),
                            checked=lambda *_, lng=lang: self._config.language == lng,
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
                            lambda *_, m=mode: self._on_mode_change(m),
                            checked=lambda *_, m=mode: self._config.mode == m,
                            radio=True,
                        )
                        for mode in _AVAILABLE_MODES
                    )
                ),
            ),
            pystray.MenuItem(
                "Качество",
                pystray.Menu(
                    *(
                        pystray.MenuItem(
                            label,
                            lambda *_, v=val: self._on_beam_size_change(v),
                            checked=lambda *_, v=val: self._config.beam_size == v,
                            radio=True,
                        )
                        for label, val in _AVAILABLE_BEAM_SIZES
                    )
                ),
            ),
            pystray.MenuItem(
                "Макс. запись",
                pystray.Menu(
                    *(
                        pystray.MenuItem(
                            label,
                            lambda *_, v=val: self._on_recording_timeout_change(v),
                            checked=lambda *_, v=val: self._config.max_recording_seconds == v,
                            radio=True,
                        )
                        for label, val in _AVAILABLE_RECORDING_TIMEOUTS
                    )
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Автопунктуация",
                self._on_auto_punctuation_toggle,
                checked=lambda _: self._config.auto_punctuation,
            ),
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
                subprocess.Popen(
                    ["open", str(config_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif sys.platform == "win32":
                os.startfile(str(config_path))
            else:
                subprocess.Popen(
                    ["xdg-open", str(config_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as exc:
            logger.error(f"Failed to open settings: {exc}")

    def _on_model_change(self, model: str) -> None:
        """Handle model menu change."""
        # pystray may pass a MenuItem object instead of a string
        if not isinstance(model, str):
            model = getattr(model, "text", None) or getattr(model, "label", None) or str(model)
        try:
            self._config = self._config.model_copy(update={"whisper_model": model})
            if self._app:
                self._app._config = self._config
                # Update pipeline config so it uses the new model name
                if self._app._pipeline is not None:
                    self._app._pipeline.config = self._config
            self._persist_and_refresh_menu()
            logger.info(f"Model changed to '{model}'")

            # Show loading indicator in tray
            self.set_model_loading(True, "Загрузка модели...")

            # Reload model in background thread — medium is 1.5 GB,
            # downloading/loading blocks the main thread (Carbon event loop)
            # for minutes if done synchronously.
            if self._app and self._app._recognition_engine:
                # Connect progress callback to update tray with percentage
                def _on_progress(pct: int) -> None:
                    self.set_model_loading(True, f"Загрузка модели {pct}%")

                self._app._recognition_engine.set_progress_callback(_on_progress)

                def _bg_reload() -> None:
                    try:
                        self._app._recognition_engine.reload(model)
                        logger.info(f"Model '{model}' reloaded successfully")
                    except Exception as exc:
                        logger.error(f"Failed to reload model '{model}': {exc}")
                    finally:
                        # Restore tray to normal state
                        self._app._recognition_engine.set_progress_callback(None)
                        self.set_model_loading(False)

                threading.Thread(target=_bg_reload, daemon=True, name="model-reload").start()
            else:
                self.set_model_loading(False)
        except Exception as exc:
            self.set_model_loading(False)
            logger.error(f"Failed to change model: {exc}")

    def _on_language_change(self, lang: str) -> None:
        """Handle language menu change."""
        # pystray may pass a MenuItem object instead of a string
        if not isinstance(lang, str):
            lang = getattr(lang, "text", None) or getattr(lang, "label", None) or str(lang)
        try:
            self._config = self._config.model_copy(update={"language": lang})
            if self._app:
                self._app._config = self._config
            self._persist_and_refresh_menu()
            logger.info(f"Language changed to '{lang}'")
        except Exception as exc:
            logger.error(f"Failed to change language: {exc}")

    def _on_mode_change(self, mode: str) -> None:
        """Handle mode menu change."""
        # pystray may pass a MenuItem object instead of a string
        if not isinstance(mode, str):
            # Try to extract the text from MenuItem
            if hasattr(mode, "text"):
                mode = mode.text
            elif hasattr(mode, "label"):
                mode = mode.label
            else:
                mode = str(mode)
        try:
            self._config = self._config.model_copy(update={"mode": mode})
            if self._app:
                self._app._config = self._config
                if self._app._pipeline is not None:
                    self._app._pipeline.change_mode(mode)
            self._persist_and_refresh_menu()
            logger.info(f"Mode changed to '{mode}'")
        except Exception as exc:
            logger.error(f"Failed to change mode: {exc}")

    def _on_beam_size_change(self, beam_size: int) -> None:
        """Handle beam size menu change — updates without reloading model."""
        try:
            self._config = self._config.model_copy(update={"beam_size": beam_size})
            if self._app:
                self._app._config = self._config
                # Update the engine's beam_size without model reload
                if self._app._recognition_engine is not None:
                    self._app._recognition_engine.set_beam_size(beam_size)
                # Update pipeline config so it propagates the new value
                if self._app._pipeline is not None:
                    self._app._pipeline.config = self._config
            self._persist_and_refresh_menu()
            logger.info(f"Beam size changed to {beam_size}")
        except Exception as exc:
            logger.error(f"Failed to change beam size: {exc}")

    def _on_recording_timeout_change(self, seconds: int) -> None:
        """Handle max recording timeout change — updates pipeline safety timer interval."""
        try:
            self._config = self._config.model_copy(update={"max_recording_seconds": seconds})
            if self._app:
                self._app._config = self._config
                # Update pipeline config — the timer will use the new value
                # on the next recording
                if self._app._pipeline is not None:
                    self._app._pipeline.config = self._config
            self._persist_and_refresh_menu()
            logger.info(f"Max recording timeout changed to {seconds}s")
        except Exception as exc:
            logger.error(f"Failed to change recording timeout: {exc}")

    def _on_auto_punctuation_toggle(self) -> None:
        """Toggle auto-punctuation on/off."""
        new_value = not self._config.auto_punctuation
        try:
            self._config = self._config.model_copy(update={"auto_punctuation": new_value})
            if self._app:
                self._app._config = self._config
                if self._app._pipeline is not None:
                    self._app._pipeline.config = self._config
            self._persist_and_refresh_menu()
            logger.info(f"Auto-punctuation {'enabled' if new_value else 'disabled'}")
        except Exception as exc:
            logger.error(f"Failed to toggle auto-punctuation: {exc}")

    def _persist_and_refresh_menu(self) -> None:
        """Persist config to file and refresh tray menu."""
        try:
            from voice_dictation.config.manager import ConfigManager

            ConfigManager().save(self._config)
        except Exception as exc:
            logger.warning(f"Failed to save config change: {exc}")
        if self._icon is not None:
            try:
                self._icon.menu = self._create_menu()
                self._icon.update_menu()
            except Exception as exc:
                logger.debug(f"Menu update failed: {exc}")
