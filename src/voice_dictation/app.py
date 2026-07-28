"""Main application orchestrator for Voice Dictation.

Connects the configuration, state machine, audio capture, recognition engine,
hotkey listener, text injector and clipboard manager into a single dictation
pipeline via the :class:`DictationPipeline` orchestrator.

The :class:`Application` supports two activation modes:

* **push_to_talk** — press and hold the hotkey to record, release to transcribe
  and inject.
* **toggle** — first press starts recording, second press stops, transcribes
  and injects.

Components are created from configuration values, but any component may be
injected via the constructor (dependency injection) which makes the class
trivially testable without real hardware.
"""

from __future__ import annotations

import signal
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from voice_dictation.audio.base import AudioCapture
from voice_dictation.audio.sounddevice_capture import SoundDeviceCapture
from voice_dictation.config.manager import ConfigManager
from voice_dictation.config.schema import AppConfig
from voice_dictation.core.state import State, StateMachine
from voice_dictation.hotkey.base import HotkeyListener
from voice_dictation.injection import create_injector
from voice_dictation.injection.base import TextInjector
from voice_dictation.pipeline import DictationPipeline
from voice_dictation.platform.detect import get_platform
from voice_dictation.recognition.base import RecognitionEngine
from voice_dictation.recognition.whisper_engine import WhisperEngine
from voice_dictation.utils.clipboard import ClipboardManager
from voice_dictation.utils.logging import setup_logging

if TYPE_CHECKING:
    pass


class Application:
    """Voice Dictation application orchestrator.

    Wires together every subsystem into a :class:`DictationPipeline` and drives
    the dictation state machine in response to global hotkey events. Designed
    for testability: any subsystem may be supplied via constructor arguments,
    otherwise it is built from configuration with graceful degradation on
    failure.
    """

    _PID_FILE = Path.home() / ".voice-dictation" / "voice-dictation.pid"

    def __init__(
        self,
        audio_capture: AudioCapture | None = None,
        recognition_engine: RecognitionEngine | None = None,
        hotkey_listener: HotkeyListener | None = None,
        text_injector: TextInjector | None = None,
        config_manager: ConfigManager | None = None,
        clipboard_manager: ClipboardManager | None = None,
    ) -> None:
        self._platform = get_platform()

        self._config_manager = config_manager or ConfigManager()
        try:
            self._config = self._config_manager.load()
        except Exception as exc:
            logger.error(f"Failed to load config, using defaults: {exc}")
            self._config = AppConfig()

        setup_logging(self._config.log_level)

        self._state_machine = StateMachine()
        self._running = False
        self._shutdown_event = threading.Event()
        self._tray: object | None = None
        self._current_hotkey: str = ""

        self._audio_capture: AudioCapture | None = audio_capture
        self._recognition_engine: RecognitionEngine | None = recognition_engine
        self._hotkey_listener: HotkeyListener | None = hotkey_listener
        self._text_injector: TextInjector | None = text_injector
        self._clipboard_manager: ClipboardManager | None = clipboard_manager
        self._pipeline: DictationPipeline | None = None

        # Only init injected components + lightweight config callbacks now.
        # Heavy components (audio, whisper, pynput) are deferred to run()
        # so the main thread can start the macOS event loop quickly.
        if all(
            c is not None
            for c in (
                self._audio_capture,
                self._recognition_engine,
                self._text_injector,
                self._hotkey_listener,
            )
        ):
            self._build_pipeline()

        self._state_machine.on_transition(self._on_state_changed)
        self._config_manager.on_reload(self._on_config_reload)

    # ------------------------------------------------------------------
    # Component initialization (deferred to background thread)
    # ------------------------------------------------------------------

    def _init_components(self) -> None:
        """Create any components not injected via the constructor.

        Called from a background thread — safe to do heavy I/O here.
        """
        if self._audio_capture is None:
            self._audio_capture = self._create_audio_capture()
        if self._recognition_engine is None:
            self._recognition_engine = self._create_recognition_engine()
        if self._text_injector is None:
            self._text_injector = self._create_text_injector()
        if self._clipboard_manager is None:
            self._clipboard_manager = self._create_clipboard_manager()
        # Hotkey listener was already created & started on the main thread — skip.
        # If it wasn't (e.g. on non-macOS or in tests), create it here.
        if self._hotkey_listener is None:
            self._hotkey_listener = self._create_hotkey_listener()

        self._build_pipeline()

    def _build_pipeline(self) -> None:
        """Assemble the pipeline from already-created components."""
        if all(
            c is not None
            for c in (
                self._audio_capture,
                self._recognition_engine,
                self._text_injector,
                self._hotkey_listener,
            )
        ):
            self._pipeline = DictationPipeline(
                state_machine=self._state_machine,
                audio_capture=self._audio_capture,  # type: ignore[arg-type]
                recognition_engine=self._recognition_engine,  # type: ignore[arg-type]
                text_injector=self._text_injector,  # type: ignore[arg-type]
                hotkey_listener=self._hotkey_listener,  # type: ignore[arg-type]
                config=self._config,
            )

    def _create_audio_capture(self) -> AudioCapture | None:
        try:
            return SoundDeviceCapture(
                sample_rate=16000,
                channels=1,
                dtype="int16",
                device_index=self._config.audio_device,
            )
        except Exception as exc:
            logger.error(f"Failed to initialize audio capture: {exc}")
            return None

    def _create_recognition_engine(self) -> RecognitionEngine | None:
        try:
            return WhisperEngine(
                model_size=self._config.whisper_model,
                device=self._config.device,
                compute_type=self._config.compute_type,
                language=self._config.language,
                initial_prompt=self._config.initial_prompt,
                model_cache_dir=self._config.model_cache_dir,
            )
        except Exception as exc:
            logger.error(f"Failed to initialize recognition engine: {exc}")
            return None

    def _create_hotkey_listener(self) -> HotkeyListener | None:
        try:
            if self._platform == "macos":
                # Use CarbonHotkeyListener on macOS — RegisterEventHotKey
                # requires no Accessibility permissions and never calls TIS,
                # so it avoids both the SIGABRT crash and the permission
                # prompt that CGEventTap suffers from.
                from voice_dictation.hotkey.carbon_listener import (
                    CarbonHotkeyListener,
                )

                return CarbonHotkeyListener(mode=self._config.mode)
            # Fallback to pynput on non-macOS platforms
            from voice_dictation.hotkey.pynput_listener import (
                PynputHotkeyListener,
            )

            return PynputHotkeyListener(mode=self._config.mode)
        except Exception as exc:
            logger.error(f"Failed to initialize hotkey listener: {exc}")
            return None

    def _create_text_injector(self) -> TextInjector | None:
        try:
            return create_injector(
                method=self._config.injection_method,
                restore_clipboard=self._config.restore_clipboard,
            )
        except Exception as exc:
            logger.error(f"Failed to initialize text injector: {exc}")
            return None

    def _create_clipboard_manager(self) -> ClipboardManager:
        return ClipboardManager()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def state_machine(self) -> StateMachine:
        return self._state_machine

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def running(self) -> bool:
        return self._running

    @property
    def audio_capture(self) -> AudioCapture | None:
        return self._audio_capture

    @property
    def recognition_engine(self) -> RecognitionEngine | None:
        return self._recognition_engine

    @property
    def hotkey_listener(self) -> HotkeyListener | None:
        return self._hotkey_listener

    @property
    def text_injector(self) -> TextInjector | None:
        return self._text_injector

    @property
    def clipboard_manager(self) -> ClipboardManager | None:
        return self._clipboard_manager

    @property
    def pipeline(self) -> DictationPipeline | None:
        return self._pipeline

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the voice dictation application.

        On macOS the main thread **must** run the event loop (pystray / AppKit)
        so that the system does not report the app as unresponsive.  The pipeline
        and all other subsystems are started in background threads.
        """
        from voice_dictation import __version__

        logger.info(f"Voice Dictation v{__version__} starting on {self._platform}")
        logger.info(f"Platform info: {sys.platform}")

        self._running = True

        # Start pipeline + config watcher in background
        self._start_background_services()

        logger.info("Voice Dictation started")
        logger.info(f"Hotkey: {self._config.hotkey} (mode: {self._config.mode})")
        logger.info(f"Model: {self._config.whisper_model} | Language: {self._config.language}")
        logger.info(f"Injection method: {self._config.injection_method}")

        # Create tray and run in main thread (blocks until quit).
        # This keeps macOS happy — the main thread processes system events.
        from voice_dictation.ui.tray import TrayIcon

        self._tray = TrayIcon(config=self._config, app=self)
        self._tray.run_blocking()

        # When tray exits (user clicked "Quit"), clean up.
        self._do_shutdown()

    def _start_background_services(self) -> None:
        """Initialise heavy components and start pipeline in background."""
        self._register_signal_handlers()

        def _init_and_start() -> None:
            """Initialise components (may take seconds) then start pipeline."""
            self._init_components()

            if self._pipeline is not None:
                self._pipeline.start()
            else:
                logger.error("Pipeline not initialised — cannot start dictation")

        threading.Thread(
            target=_init_and_start,
            daemon=True,
            name="pipeline-init",
        ).start()

        try:
            self._config_manager.start_watching()
        except Exception as exc:
            logger.error(f"Failed to start config watcher: {exc}")

    def shutdown(self) -> None:
        """Request application shutdown.

        Stops the tray icon (which unblocks the main thread) and signals
        background services to stop.
        """
        if not self._running:
            return
        logger.info("Shutdown requested...")
        self._running = False

        # Stop the tray — this will cause run_blocking() to return
        # so the main thread can proceed with cleanup.
        if self._tray is not None:
            import contextlib

            with contextlib.suppress(Exception):
                self._tray.stop()

        self._shutdown_event.set()

    def _do_shutdown(self) -> None:
        """Perform the actual cleanup after the main loop has exited."""
        logger.info("Shutting down Voice Dictation...")

        if self._pipeline is not None:
            self._pipeline.stop()

        try:
            self._config_manager.stop_watching()
        except Exception as exc:
            logger.error(f"Error stopping config watcher: {exc}")

        if self._recognition_engine is not None:
            try:
                self._recognition_engine.unload()
            except Exception as exc:
                logger.error(f"Error unloading recognition engine: {exc}")

        logger.info("Voice Dictation stopped")

    # ------------------------------------------------------------------
    # Config reload
    # ------------------------------------------------------------------

    def _on_config_reload(self, old_config: AppConfig, new_config: AppConfig) -> None:
        """Handle a configuration change at runtime."""
        logger.info("Configuration reloaded; applying changes")
        self._config = new_config

        if self._pipeline is not None:
            self._pipeline.config = new_config

        if old_config.hotkey != new_config.hotkey:
            if self._pipeline is not None:
                self._pipeline.reregister_hotkey(old_config.hotkey, new_config.hotkey)
            self._current_hotkey = new_config.hotkey

        if old_config.whisper_model != new_config.whisper_model and self._recognition_engine:
            try:
                self._recognition_engine.reload(new_config.whisper_model)
                logger.info(f"Model reloaded to '{new_config.whisper_model}'")
            except Exception as exc:
                logger.error(f"Failed to reload model: {exc}")

        if old_config.language != new_config.language:
            logger.info(f"Language changed to '{new_config.language}'")

        if old_config.mode != new_config.mode and self._hotkey_listener:
            logger.info(f"Mode changed to '{new_config.mode}' — hotkey listener may need restart")

    # ------------------------------------------------------------------
    # State / signal handling
    # ------------------------------------------------------------------

    def _on_state_changed(self, old_state: State, new_state: State) -> None:
        logger.info(f"Application state changed: {old_state.name} -> {new_state.name}")
        self._update_tray_icon(new_state)

    def _update_tray_icon(self, state: State) -> None:
        if self._tray is None:
            return
        try:
            self._tray.update_icon(state)
        except Exception as exc:
            logger.debug(f"Tray icon update failed: {exc}")

    def _register_signal_handlers(self) -> None:
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except (ValueError, OSError) as exc:
            logger.debug(f"Could not register signal handlers: {exc}")

    def _signal_handler(self, signum: int, frame) -> None:
        logger.debug(f"Received signal {signum}")
        self.shutdown()

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def set_tray(self, tray: object) -> None:
        """Attach a tray-icon controller (optional)."""
        self._tray = tray

    def _wait_for_idle(self, timeout: float = 5.0) -> bool:
        """Block until the state machine returns to IDLE or timeout expires."""
        import time

        end = time.monotonic() + timeout
        while self._state_machine.state != State.IDLE and time.monotonic() < end:
            time.sleep(0.01)
        return self._state_machine.state == State.IDLE
