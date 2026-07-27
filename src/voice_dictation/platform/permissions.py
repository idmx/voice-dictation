"""System permission checks for accessibility and microphone access."""

from loguru import logger

from voice_dictation.platform.detect import is_macos


def check_accessibility() -> bool:
    """Check if the process has accessibility permissions.

    On macOS, uses AXIsProcessTrusted().
    On Windows, always returns True (no equivalent permission needed).
    On Linux, always returns True.
    """
    if is_macos():
        try:
            from ApplicationServices import AXIsProcessTrusted  # type: ignore

            return bool(AXIsProcessTrusted())
        except ImportError:
            logger.warning(
                "PyObjC ApplicationServices not available; assuming no accessibility permission"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to check accessibility permission: {e}")
            return False
    return True


def request_accessibility() -> bool:
    """Prompt the user to grant accessibility permissions.

    On macOS, opens System Settings and triggers the trust prompt.
    Returns True if already trusted or prompt was shown.
    """
    if is_macos():
        try:
            from ApplicationServices import (  # type: ignore
                AXIsProcessTrustedWithOptions,
            )
            from CoreFoundation import (  # type: ignore
                CFDictionaryCreate,
                kCFBooleanTrue,
            )

            options = CFDictionaryCreate(
                None,
                ["AXTrustedCheckOptionPrompt"],
                [kCFBooleanTrue],
                1,
                None,
                None,
            )
            return bool(AXIsProcessTrustedWithOptions(options))
        except ImportError:
            logger.warning(
                "PyObjC ApplicationServices not available; cannot request accessibility permission"
            )
            return check_accessibility()
        except Exception as e:
            logger.error(f"Failed to request accessibility permission: {e}")
            return False
    return True


def _has_input_device() -> bool:
    """Check if any audio input device is available via sounddevice."""
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        input_devices = [d for d in devices if d["max_input_channels"] > 0] if devices else []
        return len(input_devices) > 0
    except Exception as e:
        logger.debug(f"Microphone check via sounddevice failed: {e}")
        return False


def check_microphone() -> bool:
    """Check if microphone access is available.

    On macOS, attempts to query the microphone using sounddevice.
    On Windows, checks if any audio input device is available.
    On Linux, checks if any audio input device is available.
    """
    return _has_input_device()


def request_microphone() -> bool:
    """Request microphone permission.

    On macOS, triggers the system permission dialog by attempting
    to access the microphone.
    On other platforms, returns the result of check_microphone().
    """
    if is_macos():
        try:
            import sounddevice as sd

            sd.query_devices()
            return True
        except Exception as e:
            logger.debug(f"Microphone request failed: {e}")
            return False
    return check_microphone()


def check_all_permissions() -> dict[str, bool]:
    """Check all required permissions and return a status dict."""
    return {
        "accessibility": check_accessibility(),
        "microphone": check_microphone(),
    }


def ensure_permissions() -> bool:
    """Ensure all required permissions are granted.

    Returns True if all permissions are available, False otherwise.
    On macOS, will prompt for accessibility if not granted.
    """
    if is_macos() and not check_accessibility():
        logger.info("Requesting accessibility permission...")
        request_accessibility()
        if not check_accessibility():
            logger.error("Accessibility permission not granted. Please enable in System Settings.")
            return False

    if not check_microphone():
        logger.error("No microphone available or permission not granted.")
        return False

    return True
