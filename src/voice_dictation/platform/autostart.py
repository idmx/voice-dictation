"""Auto-start registration for Voice Dictation."""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

from loguru import logger

BUNDLE_ID = "com.alfagen.voice-dictation"
LAUNCHAGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_NAME = f"{BUNDLE_ID}.plist"

REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE_NAME = "VoiceDictation"


class AutoStartManager:
    """Register or unregister Voice Dictation to start on system boot."""

    def __init__(self, app_path: str | None = None) -> None:
        self._app_path = app_path or self._detect_app_path()

    @staticmethod
    def _detect_app_path() -> str:
        """Detect the application executable path."""
        if getattr(sys, "frozen", False):
            return sys.executable
        return sys.argv[0]

    def enable(self) -> bool:
        """Enable auto-start on system boot."""
        if sys.platform == "darwin":
            return self._enable_macos()
        elif sys.platform == "win32":
            return self._enable_windows()
        else:
            logger.warning("Auto-start not supported on this platform")
            return False

    def disable(self) -> bool:
        """Disable auto-start."""
        if sys.platform == "darwin":
            return self._disable_macos()
        elif sys.platform == "win32":
            return self._disable_windows()
        else:
            logger.warning("Auto-start not supported on this platform")
            return False

    def is_enabled(self) -> bool:
        """Check if auto-start is enabled."""
        if sys.platform == "darwin":
            return self._is_enabled_macos()
        elif sys.platform == "win32":
            return self._is_enabled_windows()
        else:
            return False

    # ------------------------------------------------------------------
    # macOS — LaunchAgent plist
    # ------------------------------------------------------------------

    def _plist_path(self) -> Path:
        return LAUNCHAGENTS_DIR / PLIST_NAME

    def _build_plist(self) -> dict:
        return {
            "Label": BUNDLE_ID,
            "ProgramArguments": [self._app_path],
            "RunAtLoad": True,
            "KeepAlive": False,
            "StandardOutPath": str(Path.home() / ".voice-dictation" / "logs" / "autostart.log"),
            "StandardErrorPath": str(
                Path.home() / ".voice-dictation" / "logs" / "autostart_err.log"
            ),
        }

    def _enable_macos(self) -> bool:
        """Create LaunchAgent plist."""
        try:
            LAUNCHAGENTS_DIR.mkdir(parents=True, exist_ok=True)
            plist_path = self._plist_path()
            plist_data = self._build_plist()
            plist_path.write_bytes(plistlib.dumps(plist_data))
            logger.info(f"LaunchAgent created at {plist_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create LaunchAgent: {e}")
            return False

    def _disable_macos(self) -> bool:
        """Remove LaunchAgent plist."""
        try:
            plist_path = self._plist_path()
            if plist_path.exists():
                plist_path.unlink()
                logger.info(f"LaunchAgent removed from {plist_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove LaunchAgent: {e}")
            return False

    def _is_enabled_macos(self) -> bool:
        """Check if LaunchAgent plist exists."""
        return self._plist_path().exists()

    # ------------------------------------------------------------------
    # Windows — Registry
    # ------------------------------------------------------------------

    def _enable_windows(self) -> bool:
        """Add registry entry."""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, REGISTRY_VALUE_NAME, 0, winreg.REG_SZ, self._app_path)
            winreg.CloseKey(key)
            logger.info("Registry entry created for auto-start")
            return True
        except Exception as e:
            logger.error(f"Failed to create registry entry: {e}")
            return False

    def _disable_windows(self) -> bool:
        """Remove registry entry."""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, REGISTRY_VALUE_NAME)
            winreg.CloseKey(key)
            logger.info("Registry entry removed for auto-start")
            return True
        except FileNotFoundError:
            logger.debug("Registry entry not found, nothing to remove")
            return True
        except Exception as e:
            logger.error(f"Failed to remove registry entry: {e}")
            return False

    def _is_enabled_windows(self) -> bool:
        """Check if registry key exists."""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_READ
            )
            try:
                winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False
