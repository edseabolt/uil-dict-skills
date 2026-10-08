"""Tests for the preprocess.py extraction pipeline (offline, no subprocess)."""

import uil_dict_skills.preprocess as preprocess


def gen(*lines):
    yield from lines


def test_dictionary_words_only_drops_unnumbered():
    lines = ["A+ Spelling List", "", "12. word"]
    assert list(preprocess.dictionary_words_only(gen(*lines))) == ["12. word"]


def test_remove_number_pattern_strips_entry_number():
    assert list(preprocess.remove_number_pattern(gen("3. cat"))) == ["cat"]


def test_remove_extra_word_pattern_strips_comma_annotation():
    assert list(preprocess.remove_extra_word_pattern(gen("word, noun"))) == ["word"]


def test_remove_extra_word_pattern_strips_parenthetical():
    assert list(preprocess.remove_extra_word_pattern(gen("word (abbr.)"))) == ["word"]


def test_repair_ligatures_replaces_fi_glyph():
    # U+E022 encodes to UTF-8 b'\xee\x80\xa2', exercising both replaces
    line = "ef\ue022cient"
    results = list(preprocess.repair_ligatures(gen(line)))
    assert results == [("efficient", True)]


def test_repair_ligatures_passthrough_without_ee():
    results = list(preprocess.repair_ligatures(gen("plain")))
    assert results == [("plain", False)]


def test_preprocess_pipeline_end_to_end(monkeypatch):
    raw = ["Header line", "1. abandon, verb", "2. abolition", "3. ef\ue022cient", "Footer"]
    monkeypatch.setattr(preprocess, "run_cmd", lambda args: gen(*raw))
    results = list(preprocess.preprocess("fake.pdf"))
    assert [word for word, _repaired in results] == ["abandon", "abolition", "efficient"]
    assert [repaired for _word, repaired in results] == [False, False, True]


def test_main_writes_one_word_per_line(tmp_path, monkeypatch):
    raw = ["1. abandon", "2. ef\ue022cient"]
    monkeypatch.setattr(preprocess, "run_cmd", lambda args: gen(*raw))
    out_file = tmp_path / "words.txt"
    monkeypatch.setattr(
        "sys.argv", ["preprocess.py", "--in-file", "fake.pdf", "--out-file", str(out_file)]
    )
    preprocess.main()
    assert out_file.read_text() == "abandon\nefficient\n"
