#! /usr/bin/env python3

import argparse
import hashlib
import logging
import os
import time

from openai import OpenAI

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--in-file', required=True, type=str, help='input file containing dictionary words to convert to spoken speech')
    parser.add_argument('--max-rpm', default=50, type=int, help='maximum requests per minute that the OpenAI API provides for the given model')
    parser.add_argument('--max-time-secs', default=60, type=int, help='maximum time limit')
    parser.add_argument('--audio-format', default='flac', type=str, help='audio output format provided by OpenAI API')
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
            if num_converted == args.max_rpm:
                delta_time = time.time() - start_time
                if delta_time < args.max_time_secs:
                    wait_time = abs(args.max_time_secs - delta_time)
                    logging.info(f'waiting {wait_time} seconds ...')
                    time.sleep(wait_time)

                start_time = time.time()
                num_converted = 0

            input_word_md5 = hashlib.md5(input_word.encode('utf-8')).hexdigest()
            audio_file = os.path.join('audio', f'{index + 1}-{input_word_md5}.{args.audio_format}')

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

