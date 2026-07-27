"""Custom exceptions for voice dictation."""


class VoiceDictationError(Exception):
    """Base exception for voice dictation."""


class NotRecordingError(VoiceDictationError):
    """Attempted to stop recording when not recording."""


class AlreadyRecordingError(VoiceDictationError):
    """Attempted to start recording when already recording."""


class InvalidHotkeyError(VoiceDictationError):
    """Hotkey string could not be parsed."""


class ModelNotFoundError(VoiceDictationError):
    """Requested model is not available."""


class ModelLoadError(VoiceDictationError):
    """Failed to load the recognition model."""


class TranscriptionError(VoiceDictationError):
    """Failed to transcribe audio."""


class InjectionError(VoiceDictationError):
    """Failed to inject text into target field."""


class ClipboardError(VoiceDictationError):
    """Failed to save/restore clipboard."""


class PermissionError(VoiceDictationError):
    """Required system permission not granted."""


class ConfigError(VoiceDictationError):
    """Configuration error."""


class AudioDeviceError(VoiceDictationError):
    """Audio device error."""
