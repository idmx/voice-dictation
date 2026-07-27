"""Unit tests for logging configuration."""

from pathlib import Path
from unittest.mock import patch

from loguru import logger

from voice_dictation.utils.logging import setup_logging


class TestLoggingSetup:
    """Tests for setup_logging()."""

    def test_logging_setup(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            setup_logging(level="DEBUG")

        assert len(logger._core.handlers) >= 2

    def test_log_file_created(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            setup_logging(level="DEBUG")
            logger.info("test message for file creation")

        log_file = (
            tmp_path / ".voice-dictation" / "logs" / "voice-dictation.log"
        )
        assert log_file.exists()

    def test_log_rotation(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            setup_logging(level="DEBUG")

        handler_ids = list(logger._core.handlers.keys())
        file_handler_id = handler_ids[-1]
        handler = logger._core.handlers[file_handler_id]
        sink = handler._sink
        assert hasattr(sink, "_rotation_function")
        assert hasattr(sink, "_retention_function")

    def test_log_levels_respected(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            setup_logging(level="WARNING")
            log_file = (
                tmp_path
                / ".voice-dictation"
                / "logs"
                / "voice-dictation.log"
            )

            logger.debug("debug_should_not_appear")
            logger.info("info_should_not_appear")
            logger.warning("warning_should_appear")
            logger.error("error_should_appear")

        if log_file.exists():
            content = log_file.read_text(encoding="utf-8")
            assert "debug_should_not_appear" not in content
            assert "info_should_not_appear" not in content
            assert "warning_should_appear" in content
            assert "error_should_appear" in content
