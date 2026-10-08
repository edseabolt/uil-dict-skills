"""Tests for the preprocess.py extraction pipeline.

All tests run offline: subprocess is faked at the run_cmd boundary, so
no pdftotext binary or real PDF is involved.
"""

from collections.abc import Generator
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


def test_strip_page_artifacts_removes_readable_footer() -> None:
    """Remove the readable running footer glued to a word."""
    line = "zestfullyPage 16 \u2022 UIL A+ Spelling Word List 2024-2025"
    assert list(preprocess.strip_page_artifacts(gen(line))) == ["zestfully"]
    line = "unplugUIL A+ Spelling Word List 2024-2025 \u2022 Page 15"
    assert list(preprocess.strip_page_artifacts(gen(line))) == ["unplug"]


def test_strip_page_artifacts_removes_ciphered_footer() -> None:
    """Remove the glyph-ciphered footer (custom-encoded PDF fonts)."""
    line = "crustaceanTHK @) Rodkkhmf Vnqc Khrs 1/12,1/13 z OXfd 06"
    assert list(preprocess.strip_page_artifacts(gen(line))) == ["crustacean"]
    line = "ghostwriteOXfd 07 z THK @) Rodkkhmf Vnqc Khrs 1/12,1/13"
    assert list(preprocess.strip_page_artifacts(gen(line))) == ["ghostwrite"]


def test_strip_grade_headers_unglues_first_entry() -> None:
    """Remove a grade-section header glued to the section's first entry."""
    assert list(preprocess.strip_grade_headers(gen("Grades 5-6 1. abnormality"))) == [
        "1. abnormality"
    ]
    assert list(preprocess.strip_grade_headers(gen("Grades 3-4 (cont\u2019d) 2. next"))) == [
        "2. next"
    ]
    assert list(preprocess.strip_grade_headers(gen("2. ordinary"))) == ["2. ordinary"]


def test_numbered_entry_matches_without_space() -> None:
    """Match entries whether or not pdftotext keeps the "N. " space."""
    assert list(preprocess.dictionary_words_only(gen("2.absent", "3. present"))) == [
        "2.absent",
        "3. present",
    ]
    assert list(preprocess.remove_number_pattern(gen("2.absent"))) == ["absent"]


def test_tag_sections_tracks_current_header() -> None:
    """Attach the most recent section header to every subsequent line."""
    lines = [
        "intro",
        "Grades 3-4 1. word",
        "2.word",
        "Grades 3-4 (cont\u2019d)",
        "Grades 5-6 1. next",
    ]
    tagged = list(preprocess.tag_sections(gen(*lines)))
    assert tagged == [
        ("intro", None),
        ("Grades 3-4 1. word", "3-4"),
        ("2.word", "3-4"),
        ("Grades 3-4 (cont\u2019d)", "3-4"),
        ("Grades 5-6 1. next", "5-6"),
    ]


def gen_tagged(
    *pairs: tuple[str, str | None],
) -> Generator[tuple[str, str | None], None, None]:
    """Wrap (line, section) pairs into the shape filter_sections consumes.

    Args:
        *pairs: Tagged line tuples.

    Yields:
        Each pair in order.
    """
    yield from pairs


def test_filter_sections_keeps_only_requested() -> None:
    """Drop lines whose section was not selected; None selects everything."""
    tagged = [("a", "3-4"), ("b", "5-6"), ("c", "3-4"), ("d", None)]
    assert list(preprocess.filter_sections(gen_tagged(*tagged), frozenset({"3-4"}))) == [
        "a",
        "c",
    ]
    assert list(preprocess.filter_sections(gen_tagged(*tagged), None)) == ["a", "b", "c", "d"]


def test_preprocess_grade_filter_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extract only the requested section through the full pipeline.

    Args:
        monkeypatch: Fakes run_cmd with two grade sections of raw lines.
    """
    raw = [
        "Grades 3-4 1. cat, noun",
        "2.dog",
        "Grades 7-8 1. abdicate",
        "2. ef\ue022cient",
    ]
    monkeypatch.setattr(preprocess, "run_cmd", lambda args: gen(*raw))
    results = list(preprocess.preprocess("fake.pdf", frozenset({"7-8"})))
    assert [word for word, _ in results] == ["abdicate", "efficient"]


def test_main_grades_flag_selects_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--grades 5-6 writes only that section's words.

    Args:
        tmp_path: Temporary directory receiving the output file.
        monkeypatch: Fakes run_cmd and the CLI arguments.
    """
    raw = [
        "Grades 3-4 1. cat",
        "2.dog",
        "Grades 5-6 1. abnormality",
        "2.abode",
    ]
    monkeypatch.setattr(preprocess, "run_cmd", lambda args: gen(*raw))
    out_file = tmp_path / "words.txt"
    monkeypatch.setattr(
        "sys.argv",
        ["preprocess.py", "--in-file", "fake.pdf", "--out-file", str(out_file), "--grades", "5-6"],
    )
    preprocess.main()
    assert out_file.read_text() == "abnormality\nabode\n"


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
