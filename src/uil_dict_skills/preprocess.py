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


def preprocess(file_name: str) -> TextGeneratorWithRepair:
    """Extract cleaned dictionary words from a PDF.

    Chains the extraction stages: pdftotext, page-artifact and
    grade-header stripping, entry filtering, prefix and annotation
    stripping, and ligature repair.

    Args:
        file_name: Path to a PDF containing numbered dictionary entries.

    Yields:
        Tuples of (word, repaired) where repaired is True when a
        ligature glyph was rewritten for that word.
    """
    yield from repair_ligatures(
        remove_extra_word_pattern(
            remove_number_pattern(
                dictionary_words_only(
                    strip_grade_headers(strip_page_artifacts(run_pdftotext(file_name)))
                )
            )
        )
    )


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
    args = parser.parse_args()

    num_words = 0
    num_repaired = 0

    with open(args.out_file, "w", encoding="utf-8") as f:
        for result in preprocess(args.in_file):
            f.write(f"{result[0]}\n")
            num_words += 1
            if result[1]:
                num_repaired += 1

    logging.info(f"num_words={num_words}")
    logging.info(f"num_repaired={num_repaired}")
    logging.info("DONE!")


if __name__ == "__main__":
    main()
