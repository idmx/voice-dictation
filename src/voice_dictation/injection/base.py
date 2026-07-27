"""Abstract base class for text injection."""

from abc import ABC, abstractmethod


class TextInjector(ABC):
    """Abstract interface for injecting text into the focused field."""

    @abstractmethod
    def inject(self, text: str) -> None:
        """Inject text into the currently focused text field.

        Args:
            text: The text to inject.

        Raises:
            InjectionError: If injection fails.
        """
        ...
