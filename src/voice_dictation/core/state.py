"""Finite state machine for voice dictation workflow."""

from collections.abc import Callable
from enum import Enum, auto
from threading import Lock

from loguru import logger


class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    INJECTING = auto()


class StateMachine:
    """Thread-safe finite state machine managing the dictation pipeline."""

    VALID_TRANSITIONS: dict[State, set[State]] = {
        State.IDLE: {State.RECORDING},
        State.RECORDING: {State.TRANSCRIBING, State.IDLE},
        State.TRANSCRIBING: {State.INJECTING, State.IDLE},
        State.INJECTING: {State.IDLE},
    }

    def __init__(self) -> None:
        self._state = State.IDLE
        self._lock = Lock()
        self._callbacks: list[Callable[[State, State], None]] = []

    @property
    def state(self) -> State:
        return self._state

    def transition(self, new_state: State) -> bool:
        """Attempt a state transition. Returns True if successful."""
        with self._lock:
            if new_state not in self.VALID_TRANSITIONS.get(self._state, set()):
                logger.warning(f"Invalid transition: {self._state.name} -> {new_state.name}")
                return False
            old = self._state
            self._state = new_state
            logger.debug(f"State: {old.name} -> {new_state.name}")
            for cb in self._callbacks:
                try:
                    cb(old, new_state)
                except Exception as e:
                    logger.error(f"State callback error: {e}")
            return True

    def force_idle(self) -> None:
        """Force the state machine back to IDLE regardless of current state."""
        with self._lock:
            old = self._state
            self._state = State.IDLE
            if old != State.IDLE:
                logger.info(f"Forced state: {old.name} -> IDLE")
                for cb in self._callbacks:
                    try:
                        cb(old, State.IDLE)
                    except Exception as e:
                        logger.error(f"State callback error: {e}")

    def on_transition(self, callback: Callable[[State, State], None]) -> None:
        """Register a callback to be called on any state transition."""
        self._callbacks.append(callback)

    def can_transition(self, new_state: State) -> bool:
        """Check if a transition to new_state is valid from the current state."""
        return new_state in self.VALID_TRANSITIONS.get(self._state, set())
