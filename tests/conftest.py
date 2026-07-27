"""Pytest fixtures and configuration for voice dictation tests."""

from pathlib import Path

import pytest

from voice_dictation.config.manager import ConfigManager
from voice_dictation.config.schema import AppConfig
from voice_dictation.core.events import (
    AudioReadyEvent,
    ErrorEvent,
    HotkeyDownEvent,
    HotkeyUpEvent,
    InjectionDoneEvent,
    TranscriptReadyEvent,
)
from voice_dictation.core.state import StateMachine


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    """Provide a temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def tmp_config_manager(tmp_config_dir: Path) -> ConfigManager:
    """Provide a ConfigManager pointing to a temp directory."""
    return ConfigManager(config_dir=str(tmp_config_dir))


@pytest.fixture
def mock_state_machine() -> StateMachine:
    """Provide a fresh StateMachine instance."""
    return StateMachine()


@pytest.fixture
def sample_config() -> AppConfig:
    """Provide a sample AppConfig with non-default values."""
    return AppConfig(
        hotkey="ctrl+shift+v",
        mode="toggle",
        whisper_model="small",
        language="en",
        device="cpu",
        compute_type="float16",
        injection_method="typing",
        audio_device=0,
        sound_indicators=False,
        restore_clipboard=False,
        initial_prompt="Test prompt",
        auto_punctuation=False,
        log_level="DEBUG",
    )


@pytest.fixture
def default_config() -> AppConfig:
    """Provide a default AppConfig."""
    return AppConfig()


@pytest.fixture
def hotkey_down_event() -> HotkeyDownEvent:
    """Provide a HotkeyDownEvent."""
    return HotkeyDownEvent()


@pytest.fixture
def hotkey_up_event() -> HotkeyUpEvent:
    """Provide a HotkeyUpEvent."""
    return HotkeyUpEvent()


@pytest.fixture
def audio_ready_event() -> AudioReadyEvent:
    """Provide an AudioReadyEvent with dummy audio data."""
    return AudioReadyEvent(audio_data=b"fake_audio_data")


@pytest.fixture
def transcript_ready_event() -> TranscriptReadyEvent:
    """Provide a TranscriptReadyEvent with sample text."""
    return TranscriptReadyEvent(text="Hello, world!")


@pytest.fixture
def injection_done_event() -> InjectionDoneEvent:
    """Provide an InjectionDoneEvent."""
    return InjectionDoneEvent()


@pytest.fixture
def error_event() -> ErrorEvent:
    """Provide an ErrorEvent."""
    return ErrorEvent(message="Something went wrong")


@pytest.fixture
def fixtures_dir() -> Path:
    """Provide the path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def config_samples_dir(fixtures_dir: Path) -> Path:
    """Provide the path to config sample fixtures."""
    return fixtures_dir / "config_samples"
