#! /usr/bin/env python3

import argparse
import logging
import os
import platform
import random
import subprocess
import time

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--rest-time', default=5, type=int, help='time in seconds to rest between word utterances')
    parser.add_argument('--word-repeat', default=3, type=int, help='number of times to repeat the current word before moving to next word')
    parser.add_argument('--random', default=True, action='store_true', help='randomly pick words')
    parser.add_argument('--no-random', dest='random', action='store_false', help='words played in sorted order')
    parser.add_argument('--range', type=str, help='select range of words to use - example 10:50')
    parser.add_argument('--audio-format', default='flac', type=str, help='audio output format provided by OpenAI API')
    args = parser.parse_args()

    if not os.path.isdir('audio'):
        logging.error('audio/ directory not found — generate clips first: see README.md')
        return

    audio_files = [file for file in os.listdir('audio') if file.endswith(f'.{args.audio_format}')]
    audio_files = list(sorted(audio_files, key=lambda s: int(s.split('-')[0])))
    num_audio_files = len(audio_files)
    logging.info(f'using num_audio_files={num_audio_files}')

    if args.range:
        start_str, end_str = args.range.split(':')
        start = int(start_str) - 1 if start_str else 0
        end = int(end_str) if end_str else num_audio_files
        start = max(start, 0)
        end = min(end, num_audio_files)

        audio_files = audio_files[start:end]

    if not audio_files:
        logging.info('no audio files to play')
        return

    if args.random:
        random.shuffle(audio_files)

    system = platform.system().lower()
    exe_suffix = '.exe' if system == 'windows' else ''
    fmedia_exe = os.path.join('fmedia', system, f'fmedia{exe_suffix}')

    while audio_files:
        audio_file = os.path.join('audio', audio_files.pop(0))

        for i in range(args.word_repeat):
            logging.info(f'playing {i + 1}: {audio_file}')
            result = subprocess.run([fmedia_exe, '--notui', audio_file], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')
            result.check_returncode()
            time.sleep(args.rest_time)

    logging.info('DONE!')
        

if __name__ == '__main__':
    main()
