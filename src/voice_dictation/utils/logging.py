"""Logging configuration using loguru."""

import sys
from pathlib import Path

from loguru import logger


def setup_logging(level: str = "INFO") -> None:
    """Configure loguru with console and file output.

    File output goes to ~/.voice-dictation/logs/voice-dictation.log
    with 10 MB rotation and 7 day retention.
    """
    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # On Windows, sys.stderr may be None when running as a .exe without console
    stderr = sys.stderr
    if stderr is not None:
        logger.add(
            stderr,
            format=log_format,
            level=level,
            colorize=True,
        )

    log_dir = Path.home() / ".voice-dictation" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "voice-dictation.log"

    logger.add(
        str(log_file),
        format=log_format,
        level=level,
        rotation="10 MB",
        retention="7 days",
        compression="gz",
        encoding="utf-8",
    )

    logger.debug(f"Logging initialized at level {level} "
                 f"(stderr={'available' if stderr else 'none'})")
