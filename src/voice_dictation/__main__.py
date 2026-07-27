"""Entry point for voice-dictation."""

import sys

from voice_dictation.app import Application


def main() -> None:
    """Run the voice dictation application."""
    app = Application()
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
