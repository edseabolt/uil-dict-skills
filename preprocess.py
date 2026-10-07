#! /usr/bin/env python3

import argparse
import logging
import re
import subprocess
from typing import Generator, List, Tuple

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TextGenerator = Generator[str, None, None]
TextGeneratorWithRepair = Generator[Tuple[str, bool], None, None]

dictionary_word_pattern: re.Pattern = r'^\d+\. '
extra_word_pattern: re.Pattern = r'[,\(].*$'


def preprocess(file_name: str) -> TextGeneratorWithRepair:
    yield from repair_ligatures(remove_extra_word_pattern(remove_number_pattern(dictionary_words_only(run_pdftotext(file_name)))))


def repair_ligatures(iter: TextGenerator) -> TextGeneratorWithRepair:
    # pdftotext sometimes emits Private Use Area glyph bytes (containing
    # 0xEE) instead of the ASCII "fi" ligature; these byte substitutions
    # recover the original characters.
    for item in iter:
        tmp_item = item.encode('utf-8')
        if not b'\xee' in tmp_item:
            yield item, False
        else:
            tmp_item = tmp_item.replace(b'\xee\x80', b'f').replace(b'\xa2', b'i').replace(b'\x8d', b'').decode('utf-8')
            logging.info(f'repaired ligature: {item} -> {tmp_item}')
            yield tmp_item, True


def remove_extra_word_pattern(iter: TextGenerator) -> TextGenerator:
    for item in iter:
        tmp_item = re.sub(extra_word_pattern, '', item)
        if tmp_item == item:
            yield item
        else:
            logging.info(f'removed extra words: {item} -> {tmp_item}')
            yield tmp_item
    

def remove_number_pattern(iter: TextGenerator) -> TextGenerator:
    yield from map(lambda s: re.sub(dictionary_word_pattern, '', s), iter)


def dictionary_words_only(iter: TextGenerator) -> TextGenerator:
    for item in iter:
        if re.match(dictionary_word_pattern, item):
            yield item
        else:
            logging.info(f'removed non-dictionary item: {item}')


def run_pdftotext(file_name: str) -> TextGenerator:
    args = ['pdftotext', '-raw', '-nopgbrk', file_name, '-']
    yield from run_cmd(args)


def run_cmd(args: List[str]) -> TextGenerator:
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
