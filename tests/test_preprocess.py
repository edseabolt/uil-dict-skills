"""Tests for the preprocess.py extraction pipeline.

All tests run offline: subprocess is faked at the run_cmd boundary, so
no pdftotext binary or real PDF is involved.
"""

from pathlib import Path

import pytest

import uil_dict_skills.preprocess as preprocess


def gen(*lines: str) -> preprocess.TextGenerator:
    """Wrap string literals into the TextGenerator shape the pipeline consumes.

    Args:
        *lines: Raw pdftotext-style lines.

    Yields:
        Each line in order.
    """
    yield from lines


def test_dictionary_words_only_drops_unnumbered() -> None:
    """Keep numbered entries, drop headers and blank lines."""
    lines = ["A+ Spelling List", "", "12. word"]
    assert list(preprocess.dictionary_words_only(gen(*lines))) == ["12. word"]


def test_remove_number_pattern_strips_entry_number() -> None:
    """Remove the "N. " prefix while leaving unprefixed text intact."""
    assert list(preprocess.remove_number_pattern(gen("3. cat"))) == ["cat"]


def test_remove_extra_word_pattern_strips_comma_annotation() -> None:
    """Truncate at the first comma, keeping only the headword."""
    assert list(preprocess.remove_extra_word_pattern(gen("word, noun"))) == ["word"]


def test_remove_extra_word_pattern_strips_parenthetical() -> None:
    """Truncate at an open parenthesis, keeping only the headword."""
    assert list(preprocess.remove_extra_word_pattern(gen("word (abbr.)"))) == ["word"]


def test_repair_ligatures_replaces_fi_glyph() -> None:
    """Rewrite the pdftotext "fi" ligature glyph back to ASCII.

    U+E022 encodes to UTF-8 b"\\xee\\x80\\xa2", exercising both byte
    substitutions (ee80 -> f, a2 -> i).
    """
    line = "ef\ue022cient"  # e + fi-glyph + cient = "efficient"
    results = list(preprocess.repair_ligatures(gen(line)))
    assert results == [("efficient", True)]


def test_repair_ligatures_passthrough_without_ee() -> None:
    """Pass lines through unchanged, flagged as not repaired."""
    results = list(preprocess.repair_ligatures(gen("plain")))
    assert results == [("plain", False)]


def test_preprocess_pipeline_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every stage in sequence over faked pdftotext output.

    Args:
        monkeypatch: Replaces run_cmd so no real subprocess runs.
    """
    raw = [
        "Header line",
        "1. abandon, verb",
        "2. abolition",
        "3. ef\ue022cient",
        "Footer",
    ]
    monkeypatch.setattr(preprocess, "run_cmd", lambda args: gen(*raw))
    results = list(preprocess.preprocess("fake.pdf"))
    assert [word for word, _repaired in results] == [
        "abandon",
        "abolition",
        "efficient",
    ]
    assert [repaired for _word, repaired in results] == [False, False, True]


def test_main_writes_one_word_per_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write the cleaned word list as one word per line.

    Args:
        tmp_path: Temporary directory receiving the output file.
        monkeypatch: Fakes run_cmd and the CLI arguments.
    """
    raw = ["1. abandon", "2. ef\ue022cient"]
    monkeypatch.setattr(preprocess, "run_cmd", lambda args: gen(*raw))
    out_file = tmp_path / "words.txt"
    monkeypatch.setattr(
        "sys.argv", ["preprocess.py", "--in-file", "fake.pdf", "--out-file", str(out_file)]
    )
    preprocess.main()
    assert out_file.read_text() == "abandon\nefficient\n"
