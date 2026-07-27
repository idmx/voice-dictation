"""Recognition module."""

from voice_dictation.recognition.base import RecognitionEngine
from voice_dictation.recognition.model_manager import ModelManager
from voice_dictation.recognition.whisper_engine import WhisperEngine

__all__ = ["RecognitionEngine", "WhisperEngine", "ModelManager"]
