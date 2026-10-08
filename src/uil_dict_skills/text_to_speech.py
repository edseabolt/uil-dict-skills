"""Generate a spoken-audio deck from a word list using OpenAI TTS.

Reads a plain text file (one word per line, as produced by
preprocess.py) and creates one audio clip per word under audio/,
named "<index>-<md5-of-word>.<format>". Clips that already exist are
skipped, so the script can be re-run to fill gaps cheaply. Requests
are throttled to stay within the API's per-minute rate limit.

Example:
    $ uil-text-to-speech --in-file words.txt --max-rpm 50
"""

import argparse
import hashlib
import logging
import os
import time

from openai import OpenAI

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)


def clip_filename(index: int, word: str, audio_format: str) -> str:
    """Build the clip filename for one word.

    The md5 of the word keeps the filename stable across re-runs (so a
    partially generated deck is filled in, not duplicated); the 1-based
    index prefix preserves word-list order for play.py.

    Args:
        index: Zero-based position of the word in the input list.
        word: The word to be spoken.
        audio_format: Filename extension, e.g. "wav".

    Returns:
        Filename of the form "<index + 1>-<md5-of-word>.<ext>".
    """
    word_md5 = hashlib.md5(word.encode('utf-8')).hexdigest()
    return f'{index + 1}-{word_md5}.{audio_format}'


def main() -> None:
    '''CLI entry point: convert a word list to per-word audio clips.

    Reads the input file, then for each word computes the clip path and
    calls the OpenAI speech API only when the clip does not already
    exist. Pauses as needed to keep the request rate within --max-rpm
    per --max-time-secs seconds.
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('--in-file', required=True, type=str, help='input file containing dictionary words to convert to spoken speech')
    parser.add_argument('--max-rpm', default=50, type=int, help='maximum requests per minute that the OpenAI API provides for the given model')
    parser.add_argument('--max-time-secs', default=60, type=int, help='maximum time limit')
    parser.add_argument('--audio-format', default='wav', type=str, help='audio output format provided by OpenAI API (wav plays natively on macOS, Windows, and Linux)')
    parser.add_argument('--model', default='tts-1', type=str, help='OpenAI TTS model to use')
    parser.add_argument('--voice', default='shimmer', type=str, help='OpenAI TTS voice to use')
    args = parser.parse_args()

    with open(args.in_file) as f:
        input_words = [word.rstrip() for word in f]

    num_input_words = len(input_words)
    logging.info(f'num_input_words={num_input_words}')

    start_time = time.time()
    num_converted = 0
    num_total = 0

    with OpenAI(max_retries=3) as client:
        for index, input_word in enumerate(input_words):
            # Simple fixed-window throttle: after max_rpm requests within
            # the window, sleep out the remainder of the window.
            if num_converted == args.max_rpm:
                delta_time = time.time() - start_time
                if delta_time < args.max_time_secs:
                    wait_time = abs(args.max_time_secs - delta_time)
                    logging.info(f'waiting {wait_time} seconds ...')
                    time.sleep(wait_time)

                start_time = time.time()
                num_converted = 0

            audio_file = os.path.join('audio', clip_filename(index, input_word, args.audio_format))

            if not os.path.isfile(audio_file):
                logging.info(f'input_word={input_word}')

                response = client.audio.speech.create(
                        model=args.model,
                        voice=args.voice,
                        response_format=args.audio_format,
                        input=f'[pause]{input_word}')
                    
                response.stream_to_file(audio_file)
                num_converted += 1

            num_total += 1

            if num_total % args.max_rpm == 0:
                logging.info(f'{num_total} of {num_input_words}')

    logging.info(f'{num_total} of {num_input_words} (final)')
    logging.info('DONE!')
                    

if __name__ == '__main__':
    main()

