"""Drill the audio deck produced by text_to_speech.py.

Plays clips from audio/ (optionally a 1-based --range slice), each
spoken --word-repeat times with a pause between utterances, in random
or sorted order. Playback uses the built-in player for the host OS:
afplay on macOS, PowerShell Media.SoundPlayer on Windows, aplay on
Linux.

Example:
    $ uil-play --rest-time 5 --word-repeat 3 --range 10:50
"""

import argparse
import logging
import os
import platform
import random
import subprocess
import time

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)


def sort_key(filename: str) -> int:
    """Return the numeric index prefix of a clip filename.

    Filenames are "<index>-<md5>.<ext>"; sorting on the index restores
    the word-list order that text_to_speech.py wrote in (numeric, not
    lexicographic, so 10 sorts after 2).

    Args:
        filename: Clip filename with a numeric index prefix.

    Returns:
        The 1-based index as an int.
    """
    return int(filename.split('-')[0])


def parse_range(range_str: str, total: int) -> tuple[int, int]:
    """Convert a 1-based "start:end" range string to 0-based slice bounds.

    An empty start means the first clip; an empty end means the last.
    Bounds are clamped into [0, total].

    Args:
        range_str: Range such as "10:50", ":50", or "10:".
        total: Number of clips available.

    Returns:
        (start, end) suitable for slicing a 0-based list.

    Raises:
        ValueError: If either bound is not an integer.
    """
    start_str, end_str = range_str.split(':')
    start = int(start_str) - 1 if start_str else 0
    end = int(end_str) if end_str else total
    return max(start, 0), min(end, total)


def collect_audio_files(audio_dir: str, audio_format: str) -> list[str]:
    """List clip filenames in a directory, in word-list order.

    Args:
        audio_dir: Directory containing the generated clips.
        audio_format: Filename extension to keep, e.g. "wav".

    Returns:
        Filenames (not full paths) sorted by their numeric index prefix.
    """
    audio_files = [file for file in os.listdir(audio_dir)
                   if file.endswith(f'.{audio_format}')]
    return sorted(audio_files, key=sort_key)


def resolve_play_cmd(system: str, path: str) -> list[str] | None:
    """Build the playback command for a clip on the given platform.

    Args:
        system: Lowercased platform.system() value ("darwin",
            "windows", or "linux").
        path: Path of the audio clip to play.

    Returns:
        The argv list to execute, or None for unsupported platforms.
    """
    if system == 'darwin':
        return ['afplay', path]  # built-in
    if system == 'windows':
        # Media.SoundPlayer plays WAV; PlaySync blocks until the clip
        # finishes, which paces the word-repeat/rest loop
        escaped = path.replace("'", "''")
        script = f"(New-Object Media.SoundPlayer '{escaped}').PlaySync()"
        return ['powershell', '-NoProfile', '-Command', script]
    if system == 'linux':
        return ['aplay', '-q', path]  # built-in (ALSA)
    return None


def main() -> None:
    '''CLI entry point: run the drill loop over the audio deck.

    Loads clip filenames from audio/ ordered by their index prefix,
    applies the optional --range slice, shuffles if random play is on,
    then plays each clip --word-repeat times with --rest-time seconds
    between utterances.
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('--rest-time', default=5, type=int, help='time in seconds to rest between word utterances')
    parser.add_argument('--word-repeat', default=3, type=int, help='number of times to repeat the current word before moving to next word')
    parser.add_argument('--random', default=True, action='store_true', help='randomly pick words')
    parser.add_argument('--no-random', dest='random', action='store_false', help='words played in sorted order')
    parser.add_argument('--range', type=str, help='select range of words to use - example 10:50')
    parser.add_argument('--audio-format', default='wav', type=str, help='audio format of the clips in audio/ to play')
    args = parser.parse_args()

    if not os.path.isdir('audio'):
        logging.error('audio/ directory not found — generate clips first: see README.md')
        return

    audio_files = collect_audio_files('audio', args.audio_format)
    num_audio_files = len(audio_files)
    logging.info(f'using num_audio_files={num_audio_files}')

    if args.range:
        start, end = parse_range(args.range, num_audio_files)
        audio_files = audio_files[start:end]

    if not audio_files:
        logging.info('no audio files to play')
        return

    if args.random:
        random.shuffle(audio_files)

    system = platform.system().lower()
    if system not in ('darwin', 'windows', 'linux'):
        logging.error(f'unsupported platform: {system}')
        return

    while audio_files:
        audio_file = os.path.join('audio', audio_files.pop(0))

        for i in range(args.word_repeat):
            logging.info(f'playing {i + 1}: {audio_file}')
            result = subprocess.run(resolve_play_cmd(system, audio_file), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')
            result.check_returncode()
            time.sleep(args.rest_time)

    logging.info('DONE!')
        

if __name__ == '__main__':
    main()
