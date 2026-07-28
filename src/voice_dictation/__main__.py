"""Entry point for voice-dictation."""

import os
import sys
import threading

from loguru import logger

from voice_dictation.app import Application
from voice_dictation.core.single_instance import AlreadyRunningError, SingleInstance


def main() -> None:
    """Run the voice dictation application."""
    # Ensure only one instance runs at a time.
    single_instance = SingleInstance()
    try:
        single_instance.acquire()
    except AlreadyRunningError as exc:
        logger.error(str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    app = Application()
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()
    finally:
        single_instance.release()
        threading.Timer(3.0, lambda: os._exit(0)).start()
        sys.exit(0)


if __name__ == "__main__":
    main()
