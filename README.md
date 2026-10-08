# uil-dict-skills

Practice tool for the [UIL Dictionary Skills](https://www.uiltexas.org/academics/dictionary-skills)
test: turns the official spelling-list PDF into per-word audio clips with an
OpenAI text-to-speech voice, then drills them as randomized quiz playback.

The test asks students to identify a spelled word, its definition, or both,
from hearing it spoken. This repo automates converting the annual UIL
"A+ Spelling" list into a listening-practice deck.

## Pipeline

```
list PDF ──pdftotext──► preprocess.py ──► words.txt ──OpenAI TTS──► audio/*.flac ──► play.py (quiz)
```

## Requirements

- Python 3.12+
- [poppler](https://poppler.freedesktop.org/) — provides `pdftotext`
- An [OpenAI API key](https://platform.openai.com/api-keys) with TTS quota
- macOS (playback uses the built-in `afplay`) or Windows (bundled player included)

## Setup

```bash
./setup.sh          # creates .venv, installs deps, sanity-checks tools
cp .env.example .env
$EDITOR .env        # paste your OpenAI API key
source .env
```

## Usage

**1. Preprocess the word list.** Extract the dictionary-word lines from the
PDF, strip numbering and parentheticals, and repair ligature glyphs that
`pdftotext` mangles:

```bash
./preprocess.sh
# or directly:
.venv/bin/python preprocess.py --in-file YOUR_LIST.pdf --out-file words.txt
```

**2. Generate speech.** Each word becomes `audio/<index>-<md5>.flac`.
Existing files are skipped, so re-running only fills gaps. The script
self-throttles to stay under your model's RPM limit:

```bash
.venv/bin/python text_to_speech.py --in-file words.txt --max-rpm 50
```

**3. Drill.** Each word is spoken `--word-repeat` times with a rest between;
`--range` restricts to a slice of the list (1-based, e.g. `10:50`):

```bash
.venv/bin/python play.py --rest-time 5 --word-repeat 3 --range 10:50
```

## Bringing your own word list

This repo contains **no word lists**. The annual UIL "A+ Spelling" list is a
copyrighted compilation; download your own copy from
[uiltexas.org](https://www.uiltexas.org/academics/dictionary-skills) and pass
it to `preprocess.py`. Any line-oriented word list works — one word per
plain-text line is all `text_to_speech.py` requires.

## Repository layout

| Path | Role |
|---|---|
| `preprocess.py` | PDF → cleaned word list (generator pipeline) |
| `text_to_speech.py` | word list → per-word FLAC clips via OpenAI TTS |
| `play.py` | quiz-mode playback of the audio deck |
| `setup.sh` | venv bootstrap and tooling checks |
| `fmedia/windows/` | vendored [fmedia](https://github.com/stsaz/phiola) v1.19 player for Windows, BSD-2 |

## Playback

`play.py` picks a player by platform:

- **macOS** — the built-in `afplay`, which decodes FLAC through CoreAudio.
  No binaries required.
- **Windows** — the vendored `fmedia` v1.19 player under `fmedia/windows/`.
  Windows ships no command-line FLAC player, so this one binary is bundled
  under its BSD-2-Clause license (kept intact in that directory).

`fmedia` upstream was renamed to
[phiola](https://github.com/stsaz/phiola) and its original download channel
is gone, which is why the Windows player is vendored rather than downloaded
by a setup script. If you already have `fmedia` or `phiola` installed, edit
the `player_cmd` lines in `play.py` to point at it.

## Security

Your OpenAI key lives only in `.env` (gitignored); nothing else reads or logs
it. Never commit `.env`. Rotate the key if it ever leaks.

## License

MIT for the scripts in this repo (see `LICENSE`); the vendored Windows
`fmedia` binary remains under BSD-2-Clause with its `LICENSE` intact.
