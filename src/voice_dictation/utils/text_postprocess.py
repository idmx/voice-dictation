"""Text post-processing: auto-punctuation and formatting.

Applies language-aware punctuation rules to Whisper transcription
output, which often lacks proper capitalisation and punctuation.
"""

from __future__ import annotations

import re


def apply_auto_punctuation(text: str, language: str = "ru") -> str:
    """Apply auto-punctuation rules to transcription text.

    Rules applied:
    1. Capitalise first letter of the text
    2. Add period at end if no terminal punctuation present
    3. Capitalise after sentence-ending punctuation (.!? …)
    4. Insert commas before common conjunctions (Russian: а, но, или, что, чтобы)
    5. Clean up extra whitespace around punctuation

    Args:
        text: Raw transcription text from Whisper.
        language: Language code for language-specific rules.

    Returns:
        Text with punctuation and formatting applied.
    """
    if not text or not text.strip():
        return text

    result = text.strip()

    # 1. Capitalise first letter
    if result and result[0].islower():
        result = result[0].upper() + result[1:]

    # 2. Add period at end if no terminal punctuation
    if result and result[-1] not in ".!?:;…—–":
        result += "."

    # 3. Capitalise after sentence-ending punctuation
    result = re.sub(r"([.!?…])\s+([a-zа-яё])", _capitalize_after_sentence, result)

    # 4. Language-specific comma rules
    if language.startswith("ru"):
        result = _russian_comma_rules(result)

    # 5. Clean up whitespace around punctuation
    result = re.sub(r"\s+([.,;:!?])", r"\1", result)  # remove space before punct
    result = re.sub(r"([.,;:!?])\s{2,}", r"\1 ", result)  # single space after

    return result


def _capitalize_after_sentence(match: re.Match) -> str:
    """Capitalize the letter after sentence-ending punctuation."""
    punct = match.group(1)
    letter = match.group(2).upper()
    return f"{punct} {letter}"


def _russian_comma_rules(text: str) -> str:
    """Apply Russian-specific comma insertion rules.

    Inserts commas before common conjunctions that typically require
    a preceding comma, but only if there isn't already one.
    """
    # Conjunctions that typically need a comma before them
    # Only insert if preceded by a word character (letter) and no comma already
    conjunctions = [
        "но",  # but
        "а",  # but/and (contrastive)
        "или",  # or
        "что",  # that (subordinating)
        "чтобы",  # in order to
        "потому",  # because
        "если",  # if
        "когда",  # when
        "хотя",  # although
        "однако",  # however
    ]

    for conj in conjunctions:
        # Match: word boundary + space + conjunction, but not after comma/period/etc
        # Don't add comma if one already exists or if it's at the start of text
        pattern = r"([a-zа-яёA-ZА-ЯЁ])(\s+)(" + re.escape(conj) + r")(\s|[,.:;!?]|$)"
        replacement = r"\1,\2\3\4"
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text
