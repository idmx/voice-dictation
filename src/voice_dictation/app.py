"""Main application class for Voice Dictation."""

import signal
import sys
import threading

from loguru import logger

from voice_dictation.config.manager import ConfigManager
from voice_dictation.core.state import State, StateMachine
from voice_dictation.platform.detect import get_platform
from voice_dictation.utils.logging import setup_logging


class Application:
    """Voice Dictation application orchestrator."""

    def __init__(self) -> None:
        self._platform = get_platform()
        self._config_manager = ConfigManager()
        self._config = self._config_manager.load()
        self._state_machine = StateMachine()
        self._running = False
        self._shutdown_event = threading.Event()
        setup_logging(self._config.log_level)

    @property
    def state_machine(self) -> StateMachine:
        return self._state_machine

    @property
    def config(self):
        return self._config

    @property
    def running(self) -> bool:
        return self._running

    def run(self) -> None:
        """Start the voice dictation application."""
        logger.info(f"Voice Dictation v{self._get_version()} starting on {self._platform}")
        logger.info(f"Platform info: {sys.platform}")

        self._running = True

        self._state_machine.on_transition(self._on_state_changed)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("Voice Dictation started")
        logger.info(f"Hotkey: {self._config.hotkey} (mode: {self._config.mode})")
        logger.info(f"Model: {self._config.whisper_model} | Language: {self._config.language}")
        logger.info(f"Injection method: {self._config.injection_method}")

        self._shutdown_event.wait()

    def shutdown(self) -> None:
        """Gracefully shut down all components."""
        if not self._running:
            return

        logger.info("Shutting down Voice Dictation...")
        self._running = False
        self._state_machine.force_idle()
        self._shutdown_event.set()
        logger.info("Voice Dictation stopped")

    def _signal_handler(self, signum: int, frame) -> None:
        logger.debug(f"Received signal {signum}")
        self.shutdown()

    def _on_state_changed(self, old_state: State, new_state: State) -> None:
        logger.info(f"Application state changed: {old_state.name} -> {new_state.name}")

    @staticmethod
    def _get_version() -> str:
        from voice_dictation import __version__

        return __version__
