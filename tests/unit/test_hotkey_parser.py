"""Unit tests for hotkey_parser module."""

import pytest

from voice_dictation.core.exceptions import InvalidHotkeyError
from voice_dictation.hotkey.hotkey_parser import HotkeyCombo, KeyCode, KeyModifier, parse_hotkey


class TestParseSimple:
    def test_single_letter(self) -> None:
        result = parse_hotkey("d")
        assert result.modifiers == frozenset()
        assert result.key == KeyCode(char="d")

    def test_single_number(self) -> None:
        result = parse_hotkey("5")
        assert result.modifiers == frozenset()
        assert result.key == KeyCode(char="5")


class TestParseModifiers:
    def test_ctrl_shift_d(self) -> None:
        result = parse_hotkey("ctrl+shift+d")
        assert result.modifiers == frozenset({KeyModifier.CTRL, KeyModifier.SHIFT})
        assert result.key == KeyCode(char="d")

    def test_alt_d(self) -> None:
        result = parse_hotkey("alt+d")
        assert result.modifiers == frozenset({KeyModifier.ALT})
        assert result.key == KeyCode(char="d")


class TestParseCmdAlias:
    def test_cmd_d(self) -> None:
        result = parse_hotkey("cmd+d")
        assert result.modifiers == frozenset({KeyModifier.CMD})
        assert result.key == KeyCode(char="d")


class TestParseOptionAlias:
    def test_option_d(self) -> None:
        result = parse_hotkey("option+d")
        assert result.modifiers == frozenset({KeyModifier.ALT})
        assert result.key == KeyCode(char="d")


class TestParseSuperAlias:
    def test_super_d(self) -> None:
        result = parse_hotkey("super+d")
        assert result.modifiers == frozenset({KeyModifier.CMD})
        assert result.key == KeyCode(char="d")


class TestParseWinAlias:
    def test_win_d(self) -> None:
        result = parse_hotkey("win+d")
        assert result.modifiers == frozenset({KeyModifier.CMD})
        assert result.key == KeyCode(char="d")


class TestParseFnKey:
    def test_fn_f5(self) -> None:
        result = parse_hotkey("fn+f5")
        assert result.modifiers == frozenset({KeyModifier.FN})
        assert result.key == KeyCode(special="f5")


class TestParseEmpty:
    def test_empty_string(self) -> None:
        with pytest.raises(InvalidHotkeyError):
            parse_hotkey("")

    def test_whitespace_only(self) -> None:
        with pytest.raises(InvalidHotkeyError):
            parse_hotkey("   ")


class TestParseUnknownKey:
    def test_unknown_key(self) -> None:
        with pytest.raises(InvalidHotkeyError, match="Unknown key"):
            parse_hotkey("ctrl+xyz")

    def test_unknown_modifier_in_non_final_position(self) -> None:
        with pytest.raises(InvalidHotkeyError):
            parse_hotkey("foo+d")


class TestParseDuplicateModifiers:
    def test_ctrl_ctrl_d(self) -> None:
        result = parse_hotkey("ctrl+ctrl+d")
        assert result.modifiers == frozenset({KeyModifier.CTRL})
        assert result.key == KeyCode(char="d")


class TestParseCaseInsensitive:
    def test_mixed_case(self) -> None:
        result1 = parse_hotkey("Ctrl+Shift+D")
        result2 = parse_hotkey("ctrl+shift+d")
        assert result1 == result2

    def test_uppercase(self) -> None:
        result = parse_hotkey("CTRL+SHIFT+D")
        assert result.modifiers == frozenset({KeyModifier.CTRL, KeyModifier.SHIFT})
        assert result.key == KeyCode(char="d")


class TestParseSpecialKeys:
    def test_ctrl_space(self) -> None:
        result = parse_hotkey("ctrl+space")
        assert result.modifiers == frozenset({KeyModifier.CTRL})
        assert result.key == KeyCode(special="space")

    def test_alt_enter(self) -> None:
        result = parse_hotkey("alt+enter")
        assert result.modifiers == frozenset({KeyModifier.ALT})
        assert result.key == KeyCode(special="enter")

    def test_shift_tab(self) -> None:
        result = parse_hotkey("shift+tab")
        assert result.modifiers == frozenset({KeyModifier.SHIFT})
        assert result.key == KeyCode(special="tab")

    def test_ctrl_esc(self) -> None:
        result = parse_hotkey("ctrl+esc")
        assert result.modifiers == frozenset({KeyModifier.CTRL})
        assert result.key == KeyCode(special="esc")

    def test_backspace(self) -> None:
        result = parse_hotkey("ctrl+backspace")
        assert result.key == KeyCode(special="backspace")

    def test_delete(self) -> None:
        result = parse_hotkey("ctrl+delete")
        assert result.key == KeyCode(special="delete")

    def test_home(self) -> None:
        result = parse_hotkey("alt+home")
        assert result.key == KeyCode(special="home")

    def test_end(self) -> None:
        result = parse_hotkey("alt+end")
        assert result.key == KeyCode(special="end")

    def test_pageup(self) -> None:
        result = parse_hotkey("ctrl+pageup")
        assert result.key == KeyCode(special="page_up")

    def test_pagedown(self) -> None:
        result = parse_hotkey("ctrl+pagedown")
        assert result.key == KeyCode(special="page_down")


class TestParseFunctionKeys:
    def test_f1(self) -> None:
        result = parse_hotkey("f1")
        assert result.modifiers == frozenset()
        assert result.key == KeyCode(special="f1")

    def test_f12(self) -> None:
        result = parse_hotkey("f12")
        assert result.key == KeyCode(special="f12")

    def test_ctrl_f5(self) -> None:
        result = parse_hotkey("ctrl+f5")
        assert result.modifiers == frozenset({KeyModifier.CTRL})
        assert result.key == KeyCode(special="f5")


class TestParseArrowKeys:
    def test_ctrl_left(self) -> None:
        result = parse_hotkey("ctrl+left")
        assert result.modifiers == frozenset({KeyModifier.CTRL})
        assert result.key == KeyCode(special="left")

    def test_alt_right(self) -> None:
        result = parse_hotkey("alt+right")
        assert result.modifiers == frozenset({KeyModifier.ALT})
        assert result.key == KeyCode(special="right")

    def test_up(self) -> None:
        result = parse_hotkey("up")
        assert result.key == KeyCode(special="up")

    def test_down(self) -> None:
        result = parse_hotkey("down")
        assert result.key == KeyCode(special="down")


class TestParseMultipleModifiers:
    def test_ctrl_alt_shift_t(self) -> None:
        result = parse_hotkey("ctrl+alt+shift+t")
        assert result.modifiers == frozenset({KeyModifier.CTRL, KeyModifier.ALT, KeyModifier.SHIFT})
        assert result.key == KeyCode(char="t")

    def test_ctrl_cmd_alt(self) -> None:
        result = parse_hotkey("ctrl+cmd+alt+a")
        assert result.modifiers == frozenset({KeyModifier.CTRL, KeyModifier.CMD, KeyModifier.ALT})
        assert result.key == KeyCode(char="a")


class TestParseWhitespaceHandling:
    def test_spaces_around_plus(self) -> None:
        result = parse_hotkey("ctrl + shift + d")
        assert result.modifiers == frozenset({KeyModifier.CTRL, KeyModifier.SHIFT})
        assert result.key == KeyCode(char="d")

    def test_leading_trailing_spaces(self) -> None:
        result = parse_hotkey("  ctrl+shift+d  ")
        assert result.modifiers == frozenset({KeyModifier.CTRL, KeyModifier.SHIFT})
        assert result.key == KeyCode(char="d")


class TestKeyCodeEquality:
    def test_char_keycode_equal(self) -> None:
        assert KeyCode(char="d") == KeyCode(char="d")

    def test_char_keycode_case_insensitive(self) -> None:
        assert KeyCode(char="D") == KeyCode(char="d")

    def test_special_keycode_equal(self) -> None:
        assert KeyCode(special="space") == KeyCode(special="space")

    def test_char_vs_special_not_equal(self) -> None:
        assert KeyCode(char="space") != KeyCode(special="space")


class TestHotkeyComboEquality:
    def test_same_combos_equal(self) -> None:
        a = HotkeyCombo(modifiers=frozenset({KeyModifier.CTRL}), key=KeyCode(char="d"))
        b = HotkeyCombo(modifiers=frozenset({KeyModifier.CTRL}), key=KeyCode(char="d"))
        assert a == b

    def test_different_combos_not_equal(self) -> None:
        a = HotkeyCombo(modifiers=frozenset({KeyModifier.CTRL}), key=KeyCode(char="d"))
        b = HotkeyCombo(modifiers=frozenset({KeyModifier.ALT}), key=KeyCode(char="d"))
        assert a != b


class TestReturnAlias:
    def test_return_maps_to_enter(self) -> None:
        result = parse_hotkey("ctrl+return")
        assert result.key == KeyCode(special="enter")

    def test_escape_alias(self) -> None:
        result = parse_hotkey("ctrl+escape")
        assert result.key == KeyCode(special="esc")

    def test_pgup_alias(self) -> None:
        result = parse_hotkey("ctrl+pgup")
        assert result.key == KeyCode(special="page_up")

    def test_pgdn_alias(self) -> None:
        result = parse_hotkey("ctrl+pgdn")
        assert result.key == KeyCode(special="page_down")

    def test_del_alias(self) -> None:
        result = parse_hotkey("ctrl+del")
        assert result.key == KeyCode(special="delete")

    def test_ins_alias(self) -> None:
        result = parse_hotkey("ctrl+ins")
        assert result.key == KeyCode(special="insert")


class TestControlAlias:
    def test_control_alias(self) -> None:
        result = parse_hotkey("control+d")
        assert result.modifiers == frozenset({KeyModifier.CTRL})

    def test_command_alias(self) -> None:
        result = parse_hotkey("command+d")
        assert result.modifiers == frozenset({KeyModifier.CMD})

    def test_windows_alias(self) -> None:
        result = parse_hotkey("windows+d")
        assert result.modifiers == frozenset({KeyModifier.CMD})
