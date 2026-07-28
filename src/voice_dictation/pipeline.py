"""Dictation pipeline orchestrator.

Wires together the state machine, audio capture, recognition engine, text
injector, and hotkey listener into a single dictation pipeline. Supports both
*push-to-talk* and *toggle* activation modes.

State flow::

    IDLE ──► RECORDING ──► TRANSCRIBING ──► INJECTING ──► IDLE
      ▲          │              │                │
      └──────────┴──────────────┴────────────────┘  (on error / empty result)
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from loguru import logger

from voice_dictation.audio.base import AudioCapture
from voice_dictation.config.schema import AppConfig
from voice_dictation.core.state import State, StateMachine
from voice_dictation.hotkey.base import HotkeyListener
from voice_dictation.injection.base import TextInjector
from voice_dictation.recognition.base import RecognitionEngine

SILENCE_THRESHOLD = 100


class DictationPipeline:
    """Orchestrates the dictation pipeline: hotkey -> audio -> recognition -> injection.

    Thread-safe: hotkey callbacks arrive from pynput's thread, while
    transcription/injection run in a dedicated worker thread so the hotkey
    listener is never blocked.
    """

    def __init__(
        self,
        state_machine: StateMachine,
        audio_capture: AudioCapture,
        recognition_engine: RecognitionEngine,
        text_injector: TextInjector,
        hotkey_listener: HotkeyListener,
        config: AppConfig,
    ) -> None:
        self._state_machine = state_machine
        self._audio_capture = audio_capture
        self._recognition_engine = recognition_engine
        self._text_injector = text_injector
        self._hotkey_listener = hotkey_listener
        self._config = config

        self._pipeline_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="transcribe")
        self._error_callbacks: list[Callable[[Exception, str], None]] = []

        self._state_machine.on_transition(self._on_state_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> State:
        return self._state_machine.state

    @property
    def config(self) -> AppConfig:
        return self._config

    @config.setter
    def config(self, value: AppConfig) -> None:
        self._config = value

    def start(self) -> None:
        """Register hotkey and start listening."""
        # Recreate executor if it was previously shut down
        if self._executor._shutdown:
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="transcribe"
            )
        deactivate = self._on_hotkey_up if self._config.mode == "push_to_talk" else None
        self._hotkey_listener.register(
            self._config.hotkey,
            on_activate=self._on_hotkey_down,
            on_deactivate=deactivate,
        )
        self._hotkey_listener.start()
        logger.info(f"Pipeline started — hotkey={self._config.hotkey} mode={self._config.mode}")

    def stop(self) -> None:
        """Stop all components and return to IDLE."""
        try:
            self._hotkey_listener.stop()
        except Exception as exc:
            logger.error(f"Error stopping hotkey listener: {exc}")

        self._state_machine.force_idle()

        if self._audio_capture.is_recording():
            try:
                self._audio_capture.stop()
            except Exception as exc:
                logger.error(f"Error stopping audio capture: {exc}")

        self._executor.shutdown(wait=True)
        logger.info("Pipeline stopped")

    def on_error(self, callback: Callable[[Exception, str], None]) -> None:
        """Register a callback invoked when a pipeline error occurs."""
        self._error_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Hotkey callbacks (called from pynput's thread)
    # ------------------------------------------------------------------

    def _on_hotkey_down(self) -> None:
        """Handle hotkey press — start recording (push-to-talk) or toggle."""
        with self._pipeline_lock:
            if self._config.mode == "toggle" and self._state_machine.state == State.RECORDING:
                self._stop_and_process()
                return

            if self._state_machine.state != State.IDLE:
                logger.debug(f"Ignoring hotkey down: state is {self._state_machine.state.name}")
                return

            if not self._state_machine.transition(State.RECORDING):
                return

            try:
                self._audio_capture.start()
                logger.info("Recording started")
            except Exception as exc:
                self._handle_error(exc, "audio_start")

    def _on_hotkey_up(self) -> None:
        """Handle hotkey release — stop recording, transcribe, inject."""
        with self._pipeline_lock:
            if self._state_machine.state != State.RECORDING:
                logger.debug(f"Ignoring hotkey up: state is {self._state_machine.state.name}")
                return
            self._stop_and_process()

    # ------------------------------------------------------------------
    # Core pipeline (called under _pipeline_lock)
    # ------------------------------------------------------------------

    def _stop_and_process(self) -> None:
        """Stop audio capture and submit the audio for transcription."""
        try:
            audio_data = self._audio_capture.stop()
            logger.info("Recording stopped")
        except Exception as exc:
            self._handle_error(exc, "audio_stop")
            return

        if not self._state_machine.transition(State.TRANSCRIBING):
            return

        if audio_data is None or audio_data.size == 0 or self._is_silence(audio_data):
            logger.info("Silent or empty audio — skipping transcription")
            self._state_machine.force_idle()
            return

        self._submit_transcription(audio_data)

    def _is_silence(self, audio: np.ndarray) -> bool:
        """Return True if audio is effectively silence."""
        return bool(np.max(np.abs(audio)) < SILENCE_THRESHOLD)

    # ------------------------------------------------------------------
    # Transcription / injection (runs in worker thread)
    # ------------------------------------------------------------------

    def _submit_transcription(self, audio_data: np.ndarray) -> None:
        """Offload transcription + injection to the worker thread."""
        try:
            self._executor.submit(self._transcribe_and_inject, audio_data)
        except RuntimeError as exc:
            logger.error(f"Could not submit transcription task: {exc}")
            self._state_machine.force_idle()

    def _transcribe_and_inject(self, audio_data: np.ndarray) -> None:
        """Transcribe audio then inject the result. Runs off the hotkey thread."""
        try:
            text = self._transcribe(audio_data)
        except Exception as exc:
            self._handle_error(exc, "transcription")
            return

        if not text or not text.strip():
            logger.info("Empty transcription result — skipping injection")
            self._state_machine.force_idle()
            return

        try:
            self._inject(text)
        except Exception as exc:
            self._handle_error(exc, "injection")

    def _transcribe(self, audio: np.ndarray) -> str:
        return self._recognition_engine.transcribe(audio, language=self._config.language)

    def _inject(self, text: str) -> None:
        if not self._state_machine.transition(State.INJECTING):
            logger.warning("Could not transition to INJECTING")
            return
        try:
            self._text_injector.inject(text)
            logger.info(f"Injected text ({len(text)} chars)")
        finally:
            self._state_machine.transition(State.IDLE)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_error(self, error: Exception, context: str) -> None:
        """Handle pipeline errors gracefully: log, force idle, notify."""
        logger.error(f"Pipeline error ({context}): {error}")
        self._state_machine.force_idle()
        for cb in self._error_callbacks:
            try:
                cb(error, context)
            except Exception as cb_exc:
                logger.error(f"Error callback raised: {cb_exc}")

    # ------------------------------------------------------------------
    # State observation
    # ------------------------------------------------------------------

    def _on_state_changed(self, old_state: State, new_state: State) -> None:
        logger.debug(f"Pipeline state: {old_state.name} -> {new_state.name}")

    # ------------------------------------------------------------------
    # Config hot-reload helpers
    # ------------------------------------------------------------------

    def reregister_hotkey(self, old_hotkey: str, new_hotkey: str) -> None:
        """Unregister the old hotkey and register the new one."""
        try:
            self._hotkey_listener.unregister(old_hotkey)
        except Exception as exc:
            logger.error(f"Failed to unregister old hotkey '{old_hotkey}': {exc}")

        deactivate = self._on_hotkey_up if self._config.mode == "push_to_talk" else None
        try:
            self._hotkey_listener.register(
                new_hotkey,
                on_activate=self._on_hotkey_down,
                on_deactivate=deactivate,
            )
            logger.info(f"Hotkey re-registered: {old_hotkey} -> {new_hotkey}")
        except Exception as exc:
            logger.error(f"Failed to register new hotkey '{new_hotkey}': {exc}")

    def change_mode(self, new_mode: str) -> None:
        """Switch activation mode (push_to_talk ↔ toggle).

        Updates the listener's mode and callbacks without unregistering
        the hotkey. CarbonHotkeyListener always listens for both PRESSED
        and RELEASED events — we only need to update which callbacks
        are invoked and how the listener routes them.
        """
        old_mode = self._config.mode
        if old_mode == new_mode:
            return

        self._config = self._config.model_copy(update={"mode": new_mode})

        # Update listener mode (CarbonHotkeyListener.set_mode)
        if hasattr(self._hotkey_listener, "set_mode"):
            self._hotkey_listener.set_mode(new_mode)

        # Update callbacks on the existing registration without re-registering.
        # Re-registering (unregister+register) can cause Carbon errors.
        hotkey = self._config.hotkey
        deactivate = self._on_hotkey_up if new_mode == "push_to_talk" else None

        # Access the internal registration and update callbacks directly
        if hasattr(self._hotkey_listener, "_registrations"):
            reg = self._hotkey_listener._registrations.get(hotkey)
            if reg is not None:
                # Update the on_deactivate callback in-place
                reg.on_deactivate = deactivate
                logger.info(f"Mode changed: {old_mode} -> {new_mode} (callbacks updated)")
                return

        # Fallback: if we can't access registrations, re-register
        logger.warning("Cannot update callbacks in-place, re-registering hotkey")
        try:
            self._hotkey_listener.unregister(hotkey)
        except Exception as exc:
            logger.error(f"Failed to unregister hotkey for mode change: {exc}")

        try:
            self._hotkey_listener.register(
                hotkey,
                on_activate=self._on_hotkey_down,
                on_deactivate=deactivate,
            )
            logger.info(f"Mode changed: {old_mode} -> {new_mode}")
        except Exception as exc:
            logger.error(f"Failed to register hotkey for mode change: {exc}")

    def wait_for_idle(self, timeout: float = 5.0) -> bool:
        """Block until the state machine returns to IDLE or timeout expires."""
        import time

        end = time.monotonic() + timeout
        while self._state_machine.state != State.IDLE and time.monotonic() < end:
            time.sleep(0.01)
        return self._state_machine.state == State.IDLE
