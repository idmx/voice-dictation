"""Audio capture module."""

from voice_dictation.audio.base import AudioCapture
from voice_dictation.audio.sounddevice_capture import SoundDeviceCapture

__all__ = ["AudioCapture", "SoundDeviceCapture"]
