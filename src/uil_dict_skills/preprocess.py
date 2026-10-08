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
from typing import Generator, List, Tuple

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# A line of raw pdftotext output.
TextGenerator = Generator[str, None, None]
# A line paired with whether a ligature repair was applied to it.
TextGeneratorWithRepair = Generator[Tuple[str, bool], None, None]

# Matches the "N. " prefix of a numbered dictionary entry.
dictionary_word_pattern: str = r'^\d+\. '
# Matches annotations after the headword, e.g. ", noun" or "(abbr.)".
extra_word_pattern: str = r'[,\(].*$'


def preprocess(file_name: str) -> TextGeneratorWithRepair:
    '''Extract cleaned dictionary words from a PDF.

    Chains the extraction stages: pdftotext, entry filtering, prefix and
    annotation stripping, and ligature repair.

    Args:
        file_name: Path to a PDF containing numbered dictionary entries.

    Yields:
        Tuples of (word, repaired) where repaired is True when a
        ligature glyph was rewritten for that word.
    '''
    yield from repair_ligatures(remove_extra_word_pattern(remove_number_pattern(dictionary_words_only(run_pdftotext(file_name)))))


def repair_ligatures(iter: TextGenerator) -> TextGeneratorWithRepair:
    '''Repair "fi" ligature glyphs emitted by pdftotext.

    pdftotext sometimes emits Private Use Area glyph bytes (containing
    0xEE) instead of the ASCII "fi" ligature; these byte substitutions
    recover the original characters.

    Args:
        iter: Lines of pdftotext output.

    Yields:
        Tuples of (line, repaired) where repaired is True when a
        substitution was applied.
    '''
    for item in iter:
        tmp_item = item.encode('utf-8')
        if not b'\xee' in tmp_item:
            yield item, False
        else:
            tmp_item = tmp_item.replace(b'\xee\x80', b'f').replace(b'\xa2', b'i').replace(b'\x8d', b'').decode('utf-8')
            logging.info(f'repaired ligature: {item} -> {tmp_item}')
            yield tmp_item, True


def remove_extra_word_pattern(iter: TextGenerator) -> TextGenerator:
    '''Strip part-of-speech and abbreviation annotations from entries.

    Removes everything from the first comma or open parenthesis to the
    end of the line, leaving only the headword.

    Args:
        iter: Dictionary entry lines, e.g. "word, noun".

    Yields:
        Lines with the annotation removed, e.g. "word".
    '''
    for item in iter:
        tmp_item = re.sub(extra_word_pattern, '', item).rstrip()
        if tmp_item == item:
            yield item
        else:
            logging.info(f'removed extra words: {item} -> {tmp_item}')
            yield tmp_item
    

def remove_number_pattern(iter: TextGenerator) -> TextGenerator:
    '''Remove the "N. " entry-number prefix from each line.

    Args:
        iter: Numbered dictionary entry lines.

    Yields:
        Lines with the entry-number prefix stripped.
    '''
    yield from map(lambda s: re.sub(dictionary_word_pattern, '', s), iter)


def dictionary_words_only(iter: TextGenerator) -> TextGenerator:
    '''Filter lines down to numbered dictionary entries.

    Args:
        iter: Lines of pdftotext output.

    Yields:
        Only lines that begin with an entry number, e.g. "12. word".
        Non-matching lines are logged and dropped.
    '''
    for item in iter:
        if re.match(dictionary_word_pattern, item):
            yield item
        else:
            logging.info(f'removed non-dictionary item: {item}')


def run_pdftotext(file_name: str) -> TextGenerator:
    '''Run pdftotext on a PDF and yield its output line by line.

    Args:
        file_name: Path to the input PDF.

    Yields:
        Each non-empty line of pdftotext's raw output.

    Raises:
        subprocess.CalledProcessError: If pdftotext exits nonzero.
    '''
    args = ['pdftotext', '-raw', '-nopgbrk', file_name, '-']
    yield from run_cmd(args)


def run_cmd(args: List[str]) -> TextGenerator:
    '''Run a subprocess and yield its stdout line by line.

    Args:
        args: Command and arguments to execute.

    Yields:
        Each non-empty line of the command's stdout.

    Raises:
        subprocess.CalledProcessError: If the command exits nonzero.
        Standard error output is logged before the error is raised.
    '''
    logging.info(f'running: {args}')
    result = subprocess.run(
        args, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        encoding='utf-8')
    
    if result.stderr:
        for line in result.stderr.split('\n'):
            logging.error(line)

    result.check_returncode()

    for line in result.stdout.split('\n'):
        if line:
            yield line
    

def main() -> None:
    '''CLI entry point: preprocess a PDF into a word-list text file.

    Writes one word per line to the output file and logs the total
    word count and the number of ligature repairs applied.
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('--in-file', required=True, help='input PDF file containing dictionary words to preprocess')
    parser.add_argument('--out-file', required=True, help='output TXT file containing preprocessed dictionary words')
    args = parser.parse_args()

    num_words = 0
    num_repaired = 0

    with open(args.out_file, 'w') as f:
        for result in preprocess(args.in_file):
            f.write(f'{result[0]}\n')
            num_words += 1
            if result[1]:
                num_repaired += 1

    logging.info(f'num_words={num_words}')
    logging.info(f'num_repaired={num_repaired}')
    logging.info('DONE!')


if __name__ == '__main__':
    main()
