"""Tests for auto-start registration."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voice_dictation.platform.autostart import AutoStartManager


@pytest.fixture
def manager() -> AutoStartManager:
    """Provide an AutoStartManager with a fake app path."""
    return AutoStartManager(app_path="/usr/local/bin/voice-dictation")


@pytest.fixture
def mock_winreg() -> MagicMock:
    """Provide a MagicMock standing in for the winreg module."""
    mock = MagicMock()
    mock.HKEY_CURRENT_USER = -2147483647
    mock.KEY_SET_VALUE = 2
    mock.KEY_READ = 0x20019
    mock.REG_SZ = 1
    return mock


# ------------------------------------------------------------------
# macOS tests
# ------------------------------------------------------------------


class TestMacOSEnable:
    @patch("voice_dictation.platform.autostart.sys")
    def test_enable_macos(self, mock_sys: MagicMock, manager: AutoStartManager) -> None:
        mock_sys.platform = "darwin"

        with patch.object(Path, "mkdir"), \
             patch.object(Path, "write_bytes") as mock_write, \
             patch("voice_dictation.platform.autostart.plistlib.dumps", return_value=b"plist-data"):
            result = manager.enable()

        assert result is True
        mock_write.assert_called_once_with(b"plist-data")

    @patch("voice_dictation.platform.autostart.sys")
    def test_enable_macos_failure(
        self, mock_sys: MagicMock, manager: AutoStartManager
    ) -> None:
        mock_sys.platform = "darwin"
        with patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
            result = manager.enable()

        assert result is False


class TestMacOSDisable:
    @patch("voice_dictation.platform.autostart.sys")
    def test_disable_macos(
        self, mock_sys: MagicMock, manager: AutoStartManager
    ) -> None:
        mock_sys.platform = "darwin"
        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "unlink") as mock_unlink:
            result = manager.disable()

        assert result is True
        mock_unlink.assert_called_once()

    @patch("voice_dictation.platform.autostart.sys")
    def test_disable_macos_no_plist(
        self, mock_sys: MagicMock, manager: AutoStartManager
    ) -> None:
        mock_sys.platform = "darwin"
        with patch.object(Path, "exists", return_value=False):
            result = manager.disable()

        assert result is True


class TestMacOSIsEnabled:
    @patch("voice_dictation.platform.autostart.sys")
    def test_is_enabled_true_macos(
        self, mock_sys: MagicMock, manager: AutoStartManager
    ) -> None:
        mock_sys.platform = "darwin"
        with patch.object(Path, "exists", return_value=True):
            assert manager.is_enabled() is True

    @patch("voice_dictation.platform.autostart.sys")
    def test_is_enabled_false_macos(
        self, mock_sys: MagicMock, manager: AutoStartManager
    ) -> None:
        mock_sys.platform = "darwin"
        with patch.object(Path, "exists", return_value=False):
            assert manager.is_enabled() is False


# ------------------------------------------------------------------
# Windows tests
# ------------------------------------------------------------------


class TestWindowsEnable:
    @patch("voice_dictation.platform.autostart.sys")
    def test_enable_windows(
        self, mock_sys: MagicMock, manager: AutoStartManager, mock_winreg: MagicMock
    ) -> None:
        mock_sys.platform = "win32"
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key

        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            result = manager.enable()

        assert result is True
        mock_winreg.SetValueEx.assert_called_once()
        mock_winreg.CloseKey.assert_called_once_with(mock_key)

    @patch("voice_dictation.platform.autostart.sys")
    def test_enable_windows_failure(
        self, mock_sys: MagicMock, manager: AutoStartManager, mock_winreg: MagicMock
    ) -> None:
        mock_sys.platform = "win32"
        mock_winreg.OpenKey.side_effect = OSError("no registry")

        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            result = manager.enable()

        assert result is False


class TestWindowsDisable:
    @patch("voice_dictation.platform.autostart.sys")
    def test_disable_windows(
        self, mock_sys: MagicMock, manager: AutoStartManager, mock_winreg: MagicMock
    ) -> None:
        mock_sys.platform = "win32"
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key

        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            result = manager.disable()

        assert result is True
        mock_winreg.DeleteValue.assert_called_once()

    @patch("voice_dictation.platform.autostart.sys")
    def test_disable_windows_not_found(
        self, mock_sys: MagicMock, manager: AutoStartManager, mock_winreg: MagicMock
    ) -> None:
        mock_sys.platform = "win32"
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.DeleteValue.side_effect = FileNotFoundError()

        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            result = manager.disable()

        assert result is True


class TestWindowsIsEnabled:
    @patch("voice_dictation.platform.autostart.sys")
    def test_is_enabled_true_windows(
        self, mock_sys: MagicMock, manager: AutoStartManager, mock_winreg: MagicMock
    ) -> None:
        mock_sys.platform = "win32"
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = ("C:\\voice-dictation.exe", 1)

        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            assert manager.is_enabled() is True

    @patch("voice_dictation.platform.autostart.sys")
    def test_is_enabled_false_windows(
        self, mock_sys: MagicMock, manager: AutoStartManager, mock_winreg: MagicMock
    ) -> None:
        mock_sys.platform = "win32"
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError()

        with patch.dict(sys.modules, {"winreg": mock_winreg}):
            assert manager.is_enabled() is False
