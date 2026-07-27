"""Unit tests for platform permissions module."""

from unittest.mock import MagicMock, patch

import pytest

from voice_dictation.platform.permissions import (
    check_accessibility,
    check_all_permissions,
    check_microphone,
    ensure_permissions,
    request_accessibility,
    request_microphone,
)


class TestCheckAccessibility:
    """Tests for check_accessibility()."""

    @pytest.mark.macos
    def test_check_accessibility_granted(self) -> None:
        mock_ax = MagicMock()
        mock_ax.AXIsProcessTrusted.return_value = True
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=True,
            ),
            patch.dict("sys.modules", {"ApplicationServices": mock_ax}),
        ):
            result = check_accessibility()
            assert result is True

    @pytest.mark.macos
    def test_check_accessibility_denied(self) -> None:
        mock_ax = MagicMock()
        mock_ax.AXIsProcessTrusted.return_value = False
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=True,
            ),
            patch.dict("sys.modules", {"ApplicationServices": mock_ax}),
        ):
            result = check_accessibility()
            assert result is False

    def test_check_accessibility_non_macos(self) -> None:
        with patch(
            "voice_dictation.platform.permissions.is_macos",
            return_value=False,
        ):
            assert check_accessibility() is True

    @pytest.mark.macos
    def test_check_accessibility_import_error(self) -> None:
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=True,
            ),
            patch.dict("sys.modules", {}),
            patch("builtins.__import__", side_effect=ImportError("no PyObjC")),
        ):
            result = check_accessibility()
            assert result is False

    @pytest.mark.macos
    def test_check_accessibility_exception(self) -> None:
        mock_ax = MagicMock()
        mock_ax.AXIsProcessTrusted.side_effect = RuntimeError("system error")
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=True,
            ),
            patch.dict("sys.modules", {"ApplicationServices": mock_ax}),
        ):
            result = check_accessibility()
            assert result is False


class TestRequestAccessibility:
    """Tests for request_accessibility()."""

    @pytest.mark.macos
    def test_request_accessibility(self) -> None:
        mock_as = MagicMock()
        mock_as.AXIsProcessTrustedWithOptions.return_value = True
        mock_cf = MagicMock()
        mock_cf.CFDictionaryCreate.return_value = {"key": "val"}
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=True,
            ),
            patch.dict(
                "sys.modules",
                {"ApplicationServices": mock_as, "CoreFoundation": mock_cf},
            ),
        ):
            result = request_accessibility()
            assert result is True
            mock_as.AXIsProcessTrustedWithOptions.assert_called_once()

    def test_request_accessibility_non_macos(self) -> None:
        with patch(
            "voice_dictation.platform.permissions.is_macos",
            return_value=False,
        ):
            assert request_accessibility() is True

    @pytest.mark.macos
    def test_request_accessibility_import_error(self) -> None:
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=True,
            ),
            patch.dict("sys.modules", {}),
            patch("builtins.__import__", side_effect=ImportError("no PyObjC")),
            patch(
                "voice_dictation.platform.permissions.check_accessibility",
                return_value=False,
            ),
        ):
            result = request_accessibility()
            assert result is False


class TestCheckMicrophone:
    """Tests for check_microphone()."""

    @pytest.mark.macos
    def test_microphone_permission_macos(self) -> None:
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = [
            {"name": "Built-in Mic", "max_input_channels": 1},
            {"name": "Speaker", "max_input_channels": 0},
        ]
        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = check_microphone()
            assert result is True

    @pytest.mark.windows
    def test_microphone_permission_windows(self) -> None:
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = [
            {"name": "Mic", "max_input_channels": 2},
        ]
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=False,
            ),
            patch.dict("sys.modules", {"sounddevice": mock_sd}),
        ):
            result = check_microphone()
            assert result is True

    def test_microphone_no_devices(self) -> None:
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = [
            {"name": "Speaker", "max_input_channels": 0},
        ]
        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = check_microphone()
            assert result is False

    def test_microphone_sounddevice_error(self) -> None:
        mock_sd = MagicMock()
        mock_sd.query_devices.side_effect = OSError("no audio")
        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = check_microphone()
            assert result is False

    def test_microphone_sounddevice_import_error(self) -> None:
        with (
            patch.dict("sys.modules", {"sounddevice": None}),
            patch(
                "builtins.__import__",
                side_effect=ImportError("no sounddevice"),
            ),
        ):
            result = check_microphone()
            assert result is False


class TestRequestMicrophone:
    """Tests for request_microphone()."""

    def test_request_microphone_macos_success(self) -> None:
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = []
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=True,
            ),
            patch.dict("sys.modules", {"sounddevice": mock_sd}),
        ):
            result = request_microphone()
            assert result is True

    def test_request_microphone_macos_failure(self) -> None:
        mock_sd = MagicMock()
        mock_sd.query_devices.side_effect = OSError("denied")
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=True,
            ),
            patch.dict("sys.modules", {"sounddevice": mock_sd}),
        ):
            result = request_microphone()
            assert result is False


class TestPermissionReturnTypes:
    """All permission methods must return bool."""

    def test_permission_check_returns_bool(self) -> None:
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=False,
            ),
            patch(
                "voice_dictation.platform.permissions._has_input_device",
                return_value=True,
            ),
        ):
            assert isinstance(check_accessibility(), bool)
            assert isinstance(check_microphone(), bool)
            assert isinstance(request_accessibility(), bool)
            assert isinstance(request_microphone(), bool)

    def test_check_all_permissions_returns_dict(self) -> None:
        with (
            patch(
                "voice_dictation.platform.permissions.check_accessibility",
                return_value=True,
            ),
            patch(
                "voice_dictation.platform.permissions.check_microphone",
                return_value=False,
            ),
        ):
            result = check_all_permissions()
            assert isinstance(result, dict)
            assert "accessibility" in result
            assert "microphone" in result
            assert result["accessibility"] is True
            assert result["microphone"] is False


class TestPermissionErrorHandling:
    """System API raises -> graceful handling, returns False."""

    def test_accessibility_system_error(self) -> None:
        mock_ax = MagicMock()
        mock_ax.AXIsProcessTrusted.side_effect = OSError("kernel error")
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=True,
            ),
            patch.dict("sys.modules", {"ApplicationServices": mock_ax}),
        ):
            result = check_accessibility()
            assert result is False

    def test_microphone_system_error(self) -> None:
        mock_sd = MagicMock()
        mock_sd.query_devices.side_effect = RuntimeError("driver crash")
        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = check_microphone()
            assert result is False

    def test_ensure_permissions_accessibility_missing(self) -> None:
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=True,
            ),
            patch(
                "voice_dictation.platform.permissions.check_accessibility",
                return_value=False,
            ),
            patch(
                "voice_dictation.platform.permissions.request_accessibility",
                return_value=False,
            ),
        ):
            assert ensure_permissions() is False

    def test_ensure_permissions_microphone_missing(self) -> None:
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=False,
            ),
            patch(
                "voice_dictation.platform.permissions.check_microphone",
                return_value=False,
            ),
        ):
            assert ensure_permissions() is False

    def test_ensure_permissions_all_granted(self) -> None:
        with (
            patch(
                "voice_dictation.platform.permissions.is_macos",
                return_value=False,
            ),
            patch(
                "voice_dictation.platform.permissions.check_microphone",
                return_value=True,
            ),
        ):
            assert ensure_permissions() is True
