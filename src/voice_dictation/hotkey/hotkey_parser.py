"""Hotkey string parsing and normalization.

This module provides two equivalent APIs:

1. ``HotkeyParser`` (preferred): static helpers returning string-based
   results, e.g. ``parse("ctrl+shift+d") -> ({"ctrl", "shift"}, "d")``.
2. Legacy helpers (``parse_hotkey``, ``HotkeyCombo``, ``KeyModifier``,
   ``KeyCode``) kept for backwards compatibility with existing callers.

Both APIs share the same normalization tables, so behavior is identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from voice_dictation.core.exceptions import InvalidHotkeyError


class KeyModifier(Enum):
    """Logical modifier key (enum form)."""

    CTRL = auto()
    CMD = auto()
    ALT = auto()
    SHIFT = auto()
    FN = auto()


@dataclass(frozen=True)
class KeyCode:
    """A normalized key: either a single character or a special key name."""

    char: str | None = None
    special: str | None = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, KeyCode):
            return NotImplemented
        if self.char is not None and other.char is not None:
            return self.char.lower() == other.char.lower()
        if self.special is not None and other.special is not None:
            return self.special.lower() == other.special.lower()
        return False

    def __hash__(self) -> int:
        val = self.char or self.special or ""
        return hash(val.lower())


@dataclass(frozen=True)
class HotkeyCombo:
    """Parsed hotkey: a set of modifiers plus exactly one main key."""

    modifiers: frozenset[KeyModifier]
    key: KeyCode


# ---------------------------------------------------------------------------
# Modifier / key normalization tables (shared by both APIs)
# ---------------------------------------------------------------------------

# String modifier aliases. Canonical values are the lowercase strings used by
# the ``HotkeyParser`` API: "ctrl", "alt", "shift", "cmd", "win", "fn".
_MODIFIER_ALIASES_STR: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "shift": "shift",
    "cmd": "cmd",
    "command": "cmd",
    "super": "cmd",
    "win": "win",
    "windows": "win",
    "fn": "fn",
}

# Map canonical string modifier -> KeyModifier enum (legacy API).
_MODIFIER_ENUM_MAP: dict[str, KeyModifier] = {
    "ctrl": KeyModifier.CTRL,
    "alt": KeyModifier.ALT,
    "shift": KeyModifier.SHIFT,
    "cmd": KeyModifier.CMD,
    "win": KeyModifier.CMD,  # Windows key maps to CMD enum (both are "super").
    "fn": KeyModifier.FN,
}

# Canonical special key names (value) keyed by their aliases (key).
_SPECIAL_KEYS: dict[str, str] = {
    "space": "space",
    "enter": "enter",
    "return": "enter",
    "tab": "tab",
    "esc": "esc",
    "escape": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "home": "home",
    "end": "end",
    "pageup": "page_up",
    "page_up": "page_up",
    "pgup": "page_up",
    "pagedown": "page_down",
    "page_down": "page_down",
    "pgdn": "page_down",
    "left": "left",
    "right": "right",
    "up": "up",
    "down": "down",
    "insert": "insert",
    "ins": "insert",
}

# Function keys f1..f20.
_FUNCTION_KEYS: dict[str, str] = {f"f{i}": f"f{i}" for i in range(1, 21)}

_ALL_SPECIAL: dict[str, str] = {**_SPECIAL_KEYS, **_FUNCTION_KEYS}

# Set of all canonical modifier strings (for fast membership tests).
_MODIFIER_CANONICAL: set[str] = set(_MODIFIER_ALIASES_STR.values())


class HotkeyParser:
    """Stateless hotkey string parser.

    All methods are static and side-effect free. The parser understands strings
    of the form ``"ctrl+shift+d"``, ``"fn+f5"``, ``"cmd+space"`` etc., normalizes
    modifiers and keys to lowercase, expands aliases, and validates the result.
    """

    @staticmethod
    def normalize_modifier(mod: str) -> str:
        """Return the canonical lowercase modifier for ``mod``.

        Aliases such as ``"command"``/``"option"``/``"control"``/``"windows"``
        are mapped to their canonical forms (``"cmd"``/``"alt"``/``"ctrl"``
        /``"win"``). An already-canonical modifier is returned unchanged.

        Raises:
            InvalidHotkeyError: if ``mod`` is not a recognized modifier.
        """
        if not isinstance(mod, str):  # pragma: no cover - defensive
            raise InvalidHotkeyError(f"Modifier must be a string, got {type(mod).__name__}")
        key = mod.strip().lower()
        if key not in _MODIFIER_ALIASES_STR:
            raise InvalidHotkeyError(f"Unknown modifier: {mod!r}")
        return _MODIFIER_ALIASES_STR[key]

    @staticmethod
    def validate_key(key: str) -> str:
        """Validate and normalize a main (non-modifier) key.

        Accepts single letters (a-z), single digits (0-9), function keys
        (f1-f20) and named special keys (space, enter, tab, escape, ...).
        Returns the canonical lowercase key name.

        Raises:
            InvalidHotkeyError: if ``key`` is not a valid main key.
        """
        if not isinstance(key, str) or not key.strip():  # pragma: no cover - defensive
            raise InvalidHotkeyError(f"Key must be a non-empty string, got {key!r}")
        normalized = key.strip().lower()
        if normalized in _ALL_SPECIAL:
            return _ALL_SPECIAL[normalized]
        if len(normalized) == 1 and (normalized.isalpha() or normalized.isdigit()):
            return normalized
        raise InvalidHotkeyError(f"Unknown key: {key!r}")

    @staticmethod
    def parse(hotkey_str: str) -> tuple[set[str], str]:
        """Parse a hotkey string into ``(modifiers, key)``.

        ``modifiers`` is a ``set[str]`` of canonical modifier strings (e.g.
        ``{"ctrl", "shift"}``) and ``key`` is the canonical main key string
        (e.g. ``"d"`` or ``"f5"``).

        Raises:
            InvalidHotkeyError: if the string is empty, contains only
                modifiers (no main key), or contains an unknown key/modifier.
        """
        if not isinstance(hotkey_str, str) or not hotkey_str.strip():
            raise InvalidHotkeyError("Hotkey string cannot be empty")

        normalized = hotkey_str.strip().lower()
        parts = [p.strip() for p in normalized.split("+")]
        parts = [p for p in parts if p]

        if not parts:
            raise InvalidHotkeyError("Hotkey string cannot be empty")

        modifiers: set[str] = set()
        key: str | None = None

        for i, part in enumerate(parts):
            if part in _MODIFIER_ALIASES_STR:
                modifiers.add(HotkeyParser.normalize_modifier(part))
            elif i == len(parts) - 1:
                key = HotkeyParser.validate_key(part)
            else:
                raise InvalidHotkeyError(f"Unknown modifier or key in non-final position: {part!r}")

        if key is None:
            raise InvalidHotkeyError("Hotkey must include a non-modifier key")

        return modifiers, key

    @staticmethod
    def to_pynput_format(hotkey_str: str) -> str:
        """Convert a hotkey string to pynput ``GlobalHotKeys`` format.

        pynput uses ``<cmd>+<shift>+d`` style syntax: modifiers are wrapped in
        angle brackets, while plain characters and function keys are written
        bare. Special named keys (space, enter, ...) are also wrapped in angle
        brackets using pynput's key names.

        Raises:
            InvalidHotkeyError: if the hotkey cannot be parsed.
        """
        modifiers, key = HotkeyParser.parse(hotkey_str)

        # pynput modifier token names match our canonical strings for
        # ctrl/alt/shift/cmd; "win" -> "<cmd>" (super) and "fn" -> "<fn>".
        tokens: list[str] = []
        for mod in sorted(modifiers):
            tokens.append(f"<{mod}>")

        # Main key: characters and digits are bare; special/function keys are
        # wrapped in angle brackets using pynput's naming (underscores ok).
        if key in _ALL_SPECIAL and not (len(key) == 1 and (key.isalpha() or key.isdigit())):
            # Function keys and named special keys both use <name> in pynput.
            tokens.append(f"<{key}>")
        else:
            tokens.append(key)

        return "+".join(tokens)


# ---------------------------------------------------------------------------
# Legacy API (kept for backwards compatibility / existing callers)
# ---------------------------------------------------------------------------

# Legacy alias map: string alias -> KeyModifier enum.
_LEGACY_MODIFIER_ALIASES: dict[str, KeyModifier] = {
    alias: _MODIFIER_ENUM_MAP[canonical] for alias, canonical in _MODIFIER_ALIASES_STR.items()
}


def parse_hotkey(hotkey_str: str) -> HotkeyCombo:
    """Parse a hotkey string into a :class:`HotkeyCombo` (legacy API).

    Equivalent to :meth:`HotkeyParser.parse` but returns enum-based types.
    """
    modifiers_str, key_str = HotkeyParser.parse(hotkey_str)

    modifiers: frozenset[KeyModifier] = frozenset(_MODIFIER_ENUM_MAP[m] for m in modifiers_str)

    if len(key_str) == 1 and (key_str.isalpha() or key_str.isdigit()):
        key = KeyCode(char=key_str)
    else:
        key = KeyCode(special=key_str)

    return HotkeyCombo(modifiers=modifiers, key=key)
