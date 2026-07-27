"""Abstract base class for hotkey listeners."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable


class HotkeyListener(ABC):
    """Abstract interface for global hotkey listeners.

    Implementations register one or more hotkey combinations, each with an
    ``on_activate`` callback (and optionally ``on_deactivate``). Two modes are
    supported:

    - ``push_to_talk``: ``on_activate`` fires when the full combo is pressed,
      ``on_deactivate`` fires when it is released.
    - ``toggle``: each press toggles between activated/deactivated.
    """

    @abstractmethod
    def register(
        self,
        hotkey: str,
        on_activate: Callable[[], None],
        on_deactivate: Callable[[], None] | None = None,
    ) -> None:
        """Register a hotkey combination with activate/deactivate callbacks."""
        ...

    @abstractmethod
    def unregister(self, hotkey: str) -> None:
        """Unregister a previously registered hotkey.

        If the hotkey was not registered, this is a no-op.
        """
        ...

    @abstractmethod
    def start(self) -> None:
        """Start listening for hotkey events."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop listening and clean up resources."""
        ...

    @abstractmethod
    def is_running(self) -> bool:
        """Return whether the listener is currently running."""
        ...
