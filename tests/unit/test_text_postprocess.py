"""Unit tests for text post-processing (auto-punctuation)."""

from voice_dictation.utils.text_postprocess import apply_auto_punctuation


class TestCapitalizeFirstLetter:
    def test_capitalize_first_letter_lower(self):
        assert apply_auto_punctuation("привет мир") == "Привет мир."

    def test_already_capitalized(self):
        assert apply_auto_punctuation("Привет мир") == "Привет мир."

    def test_empty_string(self):
        assert apply_auto_punctuation("") == ""

    def test_single_word(self):
        assert apply_auto_punctuation("привет") == "Привет."


class TestAddTerminalPeriod:
    def test_add_period_no_punctuation(self):
        assert apply_auto_punctuation("Привет мир").endswith(".")

    def test_no_double_period(self):
        assert apply_auto_punctuation("Привет мир.") == "Привет мир."

    def test_no_double_question(self):
        assert apply_auto_punctuation("Привет мир?") == "Привет мир?"

    def test_no_double_exclamation(self):
        assert apply_auto_punctuation("Привет мир!") == "Привет мир!"


class TestCapitalizeAfterSentence:
    def test_capitalize_after_period(self):
        result = apply_auto_punctuation("привет. как дела")
        assert "Привет. Как дела" in result

    def test_capitalize_after_question(self):
        result = apply_auto_punctuation("как дела. отлично")
        assert "Как дела. Отлично" in result


class TestRussianCommaRules:
    def test_comma_before_no(self):
        result = apply_auto_punctuation("я пришел но не смог")
        assert "пришел, но" in result

    def test_comma_before_a(self):
        result = apply_auto_punctuation("я читал а он спал")
        assert "читал, а" in result

    def test_comma_before_chtoby(self):
        result = apply_auto_punctuation("я пришел чтобы помочь")
        assert "пришел, чтобы" in result

    def test_no_double_comma(self):
        result = apply_auto_punctuation("я пришел, но не смог")
        assert ",, но" not in result

    def test_no_comma_at_start(self):
        result = apply_auto_punctuation("но это не важно")
        assert not result.startswith(",")


class TestWhitespaceCleanup:
    def test_remove_space_before_period(self):
        result = apply_auto_punctuation("привет .")
        assert " ." not in result

    def test_single_space_after_period(self):
        result = apply_auto_punctuation("привет.  мир")
        assert ".  " not in result


class TestEnglishLanguage:
    def test_english_capitalize(self):
        result = apply_auto_punctuation("hello world", language="en")
        assert result.startswith("H")

    def test_english_period(self):
        result = apply_auto_punctuation("hello world", language="en")
        assert result.endswith(".")


class TestEdgeCases:
    def test_whitespace_only(self):
        assert apply_auto_punctuation("   ") == "   "

    def test_already_punctuated(self):
        text = "Привет, мир!"
        assert apply_auto_punctuation(text) == text

    def test_multiple_sentences(self):
        result = apply_auto_punctuation("привет. как дела. отлично")
        assert "Привет." in result
        assert "Как дела." in result
        assert "Отлично." in result
