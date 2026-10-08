"""Extract dictionary words from a UIL spelling-list PDF into a plain
text word list.

Runs pdftotext over the input PDF, keeps only numbered dictionary-entry
lines, strips the entry numbers and any parenthetical/comma-suffixed
annotations, and repairs ligature glyphs that pdftotext emits from
embedded fonts. The output is one word per line, suitable for
text_to_speech.py.

Example:
    $ uil-preprocess --in-file list.pdf --out-file words.txt
"""

import argparse
import logging
import re
import subprocess
from collections.abc import Generator

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# A line of raw pdftotext output.
TextGenerator = Generator[str, None, None]
# A line paired with whether a ligature repair was applied to it.
TextGeneratorWithRepair = Generator[tuple[str, bool], None, None]

# Matches the "N." or "N. " prefix of a numbered dictionary entry.
# The space after the period is not reliable across pdftotext
# versions, so it is optional here.
DICTIONARY_WORD_PATTERN: str = r"^\d+\.\s*"
# Matches annotations after the headword, e.g. ", noun" or "(abbr.)".
EXTRA_WORD_PATTERN: str = r"[,\(].*$"

# Matches page-footer artifacts that pdftotext glues onto word lines.
# Two shapes occur: the readable footer ("Page 16 • UIL A+ Spelling
# Word List 2024-2025") and a glyph-ciphered variant emitted when the
# PDF uses a custom-encoded font ("THK @) Rodkkhmf Vnqc Khrs" is the
# glyph-shifted "UIL A+ Spelling Word List", "OXfd" is "Page").
PAGE_ARTIFACT_PATTERN = re.compile(
    r"UIL A\+ Spelling Word List \d{4}-\d{4}(?:\s*\u2022\s*Page \d+)?"
    r"|Page \d+\s*\u2022?"
    r"|\u2022"
    r"|(?:OXfd \d+\S* z )?THK @\) Rodkkhmf Vnqc Khrs \S*,\S+(?: z OXfd \d+\S*)?"
)

# Matches a grade-section header glued to the first entry of the
# section, e.g. "Grades 5-6 1. abnormality" (or the "(cont'd)" variant).
GRADE_HEADER_PATTERN = re.compile(r"^Grades \d+-\d+(?: \(cont.d\))?\s*")

# Matches any grade-section header line, glued or bare, e.g.
# "Grades 5-6", "Grades 5-6 (cont'd)", "Grades 5-6 1. abnormality".
SECTION_HEADER_PATTERN = re.compile(r"^Grades (\d+-\d+)")

# High-school Word Power artifacts. pdftotext packs several entries onto
# one physical line, glues page numbers onto headwords, and sticks the
# running footer ("University Interscholastic League of Texas") and the
# per-section label ("Questions 1-15") onto headword lines. These shapes
# are cleaned by the high-school pipeline before the shared entry stages.
# Splits a raw line at every "N. " entry boundary, unpacking
# multi-column rows ("1. w 2. w 3. w") and glued page-digit pairs
# ("derringer301. Descartes •") into individual "N. word" fragments.
# The negative lookbehind keeps the split at the start of a number run so
# a multi-digit entry number (e.g. "301.") is not split digit by digit.
INLINE_ENTRY_SPLIT_PATTERN = re.compile(r"(?<!\d)(?=\d+\.\s)")
# A trailing " •" bullet glued to a headword, e.g. "cartesian •".
HS_BULLET_PATTERN = re.compile(r"\s*\u2022\s*$")
# Footer prose glued to a headword, e.g. "...University Interscholastic
# League of Texas" or a per-section label "...Questions 1-15".
HS_FOOTER_UNIL_PATTERN = re.compile(r"University Interscholastic League.*$")
HS_FOOTER_QUESTIONS_PATTERN = re.compile(r"Questions \d+-\d+.*$")
# Trailing page digits stuck to a lettered headword, e.g. "despine301".
# Only stripped when preceded by a letter, protecting genuine words.
HS_TRAILING_PAGE_PATTERN = re.compile(r"(?<=[A-Za-z])\d+$")


def preprocess(file_name: str, grades: frozenset[str]) -> TextGeneratorWithRepair:
    """Extract cleaned dictionary words from a PDF.

    Runs the high-school Word Power pipeline when grades is
    frozenset({"high-school"}); otherwise chains the extraction stages
    shared by the A+ grade sections: pdftotext, page-artifact stripping,
    grade-section filtering, grade-header stripping, entry filtering,
    prefix and annotation stripping, and ligature repair.

    Args:
        file_name: Path to a PDF containing numbered dictionary entries.
        grades: Grade section to keep, e.g. frozenset({"5-6"}), or
            frozenset({"high-school"}) for the high-school Word Power list.

    Raises:
        ValueError: If grades mixes "high-school" with an A+ grade
            section, which no pipeline can satisfy.

    Yields:
        Tuples of (word, repaired) where repaired is True when a
        ligature glyph was rewritten for that word.
    """
    if "high-school" in grades and grades != frozenset({"high-school"}):
        raise ValueError(f"cannot mix high-school with A+ grade sections: {sorted(grades)}")
    if grades == frozenset({"high-school"}):
        lines = split_inline_entries(run_pdftotext(file_name))
        lines = scope_word_power_list(lines)
        lines = hs_artifact_cleanup(lines)
        yield from repair_ligatures(
            remove_extra_word_pattern(remove_number_pattern(dictionary_words_only(lines)))
        )
        return
    lines = strip_page_artifacts(run_pdftotext(file_name))
    lines = filter_sections(tag_sections(lines), grades)
    lines = strip_grade_headers(lines)
    yield from repair_ligatures(
        remove_extra_word_pattern(remove_number_pattern(dictionary_words_only(lines)))
    )


def tag_sections(lines: TextGenerator) -> Generator[tuple[str, str | None], None, None]:
    """Tag each line with the grade section it belongs to.

    Args:
        lines: Lines of pdftotext output.

    Yields:
        Tuples of (line, section) where section is the grade band
        (e.g. "5-6") of the most recent section header, or None for
        lines before the first header.
    """
    section = None
    for line in lines:
        match = SECTION_HEADER_PATTERN.match(line)
        if match:
            section = match.group(1)
        yield line, section


def filter_sections(
    tagged: Generator[tuple[str, str | None], None, None], grades: frozenset[str]
) -> TextGenerator:
    """Drop lines outside the requested grade sections.

    Args:
        tagged: (line, section) pairs from tag_sections.
        grades: Grade sections to keep.

    Yields:
        Lines whose section is selected.
    """
    for line, section in tagged:
        if section in grades:
            yield line


def strip_page_artifacts(lines: TextGenerator) -> TextGenerator:
    """Remove page-footer artifacts glued to word lines by pdftotext.

    pdftotext output can merge the running footer ("Page N • UIL A+
    Spelling Word List YYYY-YYYY") onto the same line as a word. Left
    in place, the merged text passes downstream as a bogus "word".

    Args:
        lines: Lines of pdftotext output.

    Yields:
        Lines with footer text removed; empty results are dropped.
    """
    for line in lines:
        cleaned = PAGE_ARTIFACT_PATTERN.sub("", line).strip()
        if cleaned != line.strip():
            logging.info(f"stripped page artifacts: {line!r} -> {cleaned!r}")
        if cleaned:
            yield cleaned


def strip_grade_headers(lines: TextGenerator) -> TextGenerator:
    """Remove grade-section headers glued to the section's first entry.

    pdftotext output can merge the section header onto the first entry,
    e.g. "Grades 5-6 1. abnormality", which would otherwise fail the
    numbered-entry filter.

    Args:
        lines: Lines of pdftotext output.

    Yields:
        Lines with a leading "Grades X-Y" header removed.
    """
    for line in lines:
        cleaned = GRADE_HEADER_PATTERN.sub("", line)
        if cleaned != line:
            logging.info(f"stripped grade header: {line!r} -> {cleaned!r}")
        yield cleaned


def split_inline_entries(lines: TextGenerator) -> TextGenerator:
    """Split raw lines on every "N. " entry boundary.

    The high-school list packs several entries onto one physical line
    (column counts vary by year) and glues page numbers onto headwords,
    so a single pdftotext line can hold many entries. re.split at each
    lookahead "N. " yields every entry fragment on its own line. The A+
    path never calls this: its raw output has no multi-entry lines.

    Args:
        lines: Raw pdftotext lines.

    Yields:
        Individual "N. word" fragments.
    """
    for line in lines:
        for fragment in re.split(INLINE_ENTRY_SPLIT_PATTERN, line):
            if fragment:
                yield fragment.strip()


# Matches a numbered entry fragment, e.g. "12. word". Group 1 is the
# entry number, group 2 the rest of the fragment.
HS_ENTRY_PATTERN = re.compile(r"^(\d+)\.\s*(.*)$")

# The high-school list packs its entries into parallel columns with a
# fixed stride (e.g. "1. w 51. w 101. w" on one line, "2. w 52. w 102. w"
# on the next), so entry numbers do not increase line to line. Entries
# are collected and emitted in entry-number order instead.
# An entry numbered 1 starts the real list only if an entry numbered 2
# appears within this many subsequent fragments; front matter (e.g. the
# lone "778. kookaburra •" example) has no such 1-then-2 pair.
HS_START_LOOKAHEAD: int = 6
# Stop collecting after this many consecutive fragments whose entry
# numbers were already seen: the "Sample Test Questions" block that
# follows entry 1500 reuses small numbers (7., 8., ...), so two dups in
# a row mark the end of the real list.
HS_STOP_DUPLICATES = 2
# The real Word Power list contains ~1500 entries; a shorter collected
# list means the start detection or scoping misfired.
HS_EXPECTED_MIN_ENTRIES = 500
# Entry numbers larger than this cannot be real: pdftotext glues the
# page number onto the first entry of a page ("71051. radicchio" is
# page 7 glued to "1051. radicchio"). Leading digits are stripped until
# the number fits, recovering the entry number.
HS_MAX_ENTRY = 2000


def _parse_hs_entry(fragment: str) -> tuple[int, str] | None:
    """Parse an entry fragment into (number, headword text).

    Salvages page-number glue: when the parsed number exceeds
    HS_MAX_ENTRY, leading digits are stripped (and logged) until the
    number fits a plausible entry. Returns None for non-entry fragments
    (prose, bare page numbers).

    Args:
        fragment: A single line or fragment.

    Returns:
        (number, text), or None when the fragment is not an entry.
    """
    match = HS_ENTRY_PATTERN.match(fragment.strip())
    if not match:
        return None
    digits = match.group(1)
    num = int(digits)
    if num > HS_MAX_ENTRY:
        while digits and int(digits) > HS_MAX_ENTRY:
            digits = digits[1:]
        if not digits:
            logging.warning(f"dropped unparseable entry fragment: {fragment!r}")
            return None
        logging.info(f"salvaged page-glued entry number: {num} -> {digits}")
        num = int(digits)
    return num, match.group(2).strip()


def scope_word_power_list(lines: TextGenerator) -> TextGenerator:
    """Keep only the high-school list's numbered entries, in list order.

    The raw dump contains front-matter examples, glued page-leftover
    fragments, bare page-number lines, and a numbered "Sample Test
    Questions" block that reuses small entry numbers after the real list
    ends at 1500. The list starts at the first entry numbered 1 that is
    followed by an entry numbered 2 within a few fragments (which skips
    front matter like "778. kookaburra"); collection stops at the first
    run of already-seen entry numbers (the sample-test prose). Because
    the printed list packs entries into parallel columns, fragments are
    re-emitted sorted by entry number, which restores list order.

    Args:
        lines: Entry fragments from split_inline_entries.

    Yields:
        "N. word" fragments in entry-number order.
    """
    parsed = [pair for line in lines if (pair := _parse_hs_entry(line)) is not None]

    start = None
    for index, (num, _text) in enumerate(parsed):
        if num == 1 and any(n == 2 for n, _t in parsed[index + 1 : index + 1 + HS_START_LOOKAHEAD]):
            start = index
            break
    if start is None:
        logging.error("no high-school list start found: no 1./2. entry pair")
        return

    collected: dict[int, str] = {}
    duplicates = 0
    for num, text in parsed[start:]:
        if num in collected:
            duplicates += 1
            if duplicates >= HS_STOP_DUPLICATES:
                break
            continue
        duplicates = 0
        collected[num] = text

    if len(collected) < HS_EXPECTED_MIN_ENTRIES:
        logging.warning(f"high-school list yielded only {len(collected)} entries; expected ~1500")
    for num in sorted(collected):
        yield f"{num}. {collected[num]}"


def hs_artifact_cleanup(lines: TextGenerator) -> TextGenerator:
    """Strip high-school Word Power artifacts from entry fragments.

    Removes trailing " •" bullets, footer prose glued to a headword
    ("...University Interscholastic League..."), a per-section label
    ("...Questions 1-15"), and trailing page digits stuck to a lettered
    headword (e.g. "despine301"). Empty results are dropped.

    Args:
        lines: Entry fragments from scope_word_power_list.

    Yields:
        Fragments with artifacts removed.
    """
    for line in lines:
        cleaned = HS_BULLET_PATTERN.sub("", line)
        cleaned = HS_FOOTER_UNIL_PATTERN.sub("", cleaned)
        cleaned = HS_FOOTER_QUESTIONS_PATTERN.sub("", cleaned)
        cleaned = HS_TRAILING_PAGE_PATTERN.sub("", cleaned).strip()
        if cleaned:
            yield cleaned


def repair_ligatures(lines: TextGenerator) -> TextGeneratorWithRepair:
    """Repair "fi" ligature glyphs emitted by pdftotext.

    pdftotext sometimes emits Private Use Area glyph bytes (containing
    0xEE) instead of the ASCII "fi" ligature; these byte substitutions
    recover the original characters.

    Args:
        lines: Lines of pdftotext output.

    Yields:
        Tuples of (line, repaired) where repaired is True when a
        substitution was applied.
    """
    for item in lines:
        raw_item = item.encode("utf-8")
        if b"\xee" not in raw_item:
            yield item, False
        else:
            repaired_item = (
                raw_item.replace(b"\xee\x80", b"f")
                .replace(b"\xa2", b"i")
                .replace(b"\x8d", b"")
                .decode("utf-8")
            )
            logging.info(f"repaired ligature: {item} -> {repaired_item}")
            yield repaired_item, True


def remove_extra_word_pattern(lines: TextGenerator) -> TextGenerator:
    """Strip part-of-speech and abbreviation annotations from entries.

    Removes everything from the first comma or open parenthesis to the
    end of the line, leaving only the headword.

    Args:
        lines: Dictionary entry lines, e.g. "word, noun".

    Yields:
        Lines with the annotation removed, e.g. "word".
    """
    for item in lines:
        tmp_item = re.sub(EXTRA_WORD_PATTERN, "", item).rstrip()
        if tmp_item == item:
            yield item
        else:
            logging.info(f"removed extra words: {item} -> {tmp_item}")
            yield tmp_item


def remove_number_pattern(lines: TextGenerator) -> TextGenerator:
    """Remove the "N. " entry-number prefix from each line.

    Args:
        lines: Numbered dictionary entry lines.

    Yields:
        Lines with the entry-number prefix stripped.
    """
    yield from map(lambda s: re.sub(DICTIONARY_WORD_PATTERN, "", s), lines)


def dictionary_words_only(lines: TextGenerator) -> TextGenerator:
    """Filter lines down to numbered dictionary entries.

    Args:
        lines: Lines of pdftotext output.

    Yields:
        Only lines that begin with an entry number, e.g. "12. word".
        Non-matching lines are logged and dropped.
    """
    for item in lines:
        if re.match(DICTIONARY_WORD_PATTERN, item):
            yield item
        else:
            logging.info(f"removed non-dictionary item: {item}")


def run_pdftotext(file_name: str) -> TextGenerator:
    """Run pdftotext on a PDF and yield its output line by line.

    Args:
        file_name: Path to the input PDF.

    Yields:
        Each non-empty line of pdftotext's raw output.

    Raises:
        subprocess.CalledProcessError: If pdftotext exits nonzero.
    """
    args = ["pdftotext", "-raw", "-nopgbrk", file_name, "-"]
    yield from run_cmd(args)


def run_cmd(args: list[str]) -> TextGenerator:
    """Run a subprocess and yield its stdout line by line.

    Args:
        args: Command and arguments to execute.

    Yields:
        Each non-empty line of the command's stdout.

    Raises:
        subprocess.CalledProcessError: If the command exits nonzero.
        Standard error output is logged before the error is raised.
    """
    logging.info(f"running: {args}")
    # check=False: CalledProcessError is raised manually below so the
    # collected stderr is logged first.
    result = subprocess.run(
        args, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8"
    )

    if result.stderr:
        for line in result.stderr.split("\n"):
            logging.error(line)

    result.check_returncode()

    for line in result.stdout.split("\n"):
        if line:
            yield line


def main() -> None:
    """CLI entry point: preprocess a PDF into a word-list text file.

    Writes one word per line to the output file and logs the total
    word count and the number of ligature repairs applied.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in-file", required=True, help="input PDF file containing dictionary words to preprocess"
    )
    parser.add_argument(
        "--out-file", required=True, help="output TXT file containing preprocessed dictionary words"
    )
    parser.add_argument(
        "--grades",
        choices=["3-4", "5-6", "7-8", "high-school"],
        required=True,
        help="grade section to extract; use 'high-school' for the high-school " "Word Power list",
    )
    args = parser.parse_args()

    grades = frozenset({args.grades})
    logging.info(f"grades={args.grades}")

    num_words = 0
    num_repaired = 0

    with open(args.out_file, "w", encoding="utf-8") as f:
        for result in preprocess(args.in_file, grades):
            f.write(f"{result[0]}\n")
            num_words += 1
            if result[1]:
                num_repaired += 1

    logging.info(f"num_words={num_words}")
    logging.info(f"num_repaired={num_repaired}")
    logging.info("DONE!")


if __name__ == "__main__":
    main()
