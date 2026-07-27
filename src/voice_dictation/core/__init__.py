"""Core module — state machine, events, exceptions."""

from voice_dictation.core.events import (
    AudioReadyEvent,
    ErrorEvent,
    Event,
    EventType,
    HotkeyDownEvent,
    HotkeyUpEvent,
    InjectionDoneEvent,
    TranscriptReadyEvent,
)
from voice_dictation.core.exceptions import (
    AlreadyRecordingError,
    AudioDeviceError,
    ClipboardError,
    ConfigError,
    InjectionError,
    InvalidHotkeyError,
    ModelLoadError,
    ModelNotFoundError,
    NotRecordingError,
    PermissionError,
    TranscriptionError,
    VoiceDictationError,
)
from voice_dictation.core.state import State, StateMachine

__all__ = [
    "State",
    "StateMachine",
    "Event",
    "EventType",
    "HotkeyDownEvent",
    "HotkeyUpEvent",
    "AudioReadyEvent",
    "TranscriptReadyEvent",
    "InjectionDoneEvent",
    "ErrorEvent",
    "VoiceDictationError",
    "NotRecordingError",
    "AlreadyRecordingError",
    "InvalidHotkeyError",
    "ModelNotFoundError",
    "ModelLoadError",
    "TranscriptionError",
    "InjectionError",
    "ClipboardError",
    "PermissionError",
    "ConfigError",
    "AudioDeviceError",
]
