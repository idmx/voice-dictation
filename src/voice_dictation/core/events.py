"""Event system for voice dictation."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class EventType(Enum):
    HOTKEY_DOWN = auto()
    HOTKEY_UP = auto()
    AUDIO_READY = auto()
    TRANSCRIPT_READY = auto()
    INJECTION_DONE = auto()
    ERROR = auto()
    STATE_CHANGED = auto()


@dataclass
class Event:
    type: EventType
    data: Any = None


@dataclass
class HotkeyDownEvent(Event):
    def __init__(self) -> None:
        super().__init__(type=EventType.HOTKEY_DOWN)


@dataclass
class HotkeyUpEvent(Event):
    def __init__(self) -> None:
        super().__init__(type=EventType.HOTKEY_UP)


@dataclass
class AudioReadyEvent(Event):
    audio_data: Any = None

    def __init__(self, audio_data: Any) -> None:
        super().__init__(type=EventType.AUDIO_READY, data=audio_data)
        self.audio_data = audio_data


@dataclass
class TranscriptReadyEvent(Event):
    text: str = ""

    def __init__(self, text: str) -> None:
        super().__init__(type=EventType.TRANSCRIPT_READY, data=text)
        self.text = text


@dataclass
class InjectionDoneEvent(Event):
    def __init__(self) -> None:
        super().__init__(type=EventType.INJECTION_DONE)


@dataclass
class ErrorEvent(Event):
    message: str = ""
    exception: Exception | None = None

    def __init__(self, message: str, exception: Exception | None = None) -> None:
        super().__init__(type=EventType.ERROR, data=message)
        self.message = message
        self.exception = exception
