# uil-dict-skills

Practice tool for the [UIL Dictionary Skills](https://www.uiltexas.org/academics/dictionary-skills)
test: turns the official spelling-list PDF into per-word audio clips with an
OpenAI text-to-speech voice, then drills them as randomized quiz playback.

The test asks students to identify a spelled word, its definition, or both,
from hearing it spoken. This repo automates converting the annual UIL
"A+ Spelling" list into a listening-practice deck.

## Pipeline

```
list PDF ──pdftotext──► preprocess.py ──► words.txt ──OpenAI TTS──► audio/*.wav ──► play.py (quiz)
```

## Requirements

- Python 3.10+ (3.12+ recommended)
- [poppler](https://poppler.freedesktop.org/) — provides `pdftotext`
  - **macOS** — `brew install poppler`
  - **Windows** — download the latest `Release-xx.yy.zz-0.zip` from
    [poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases),
    unzip it, and add its `Library/bin` folder to your `PATH`
  - **Linux** — `sudo apt install poppler-utils` (Debian/Ubuntu),
    `sudo dnf install poppler-utils` (Fedora), or
    `sudo pacman -S poppler` (Arch)
- An [OpenAI API key](https://platform.openai.com/api-keys) with TTS quota
- macOS, Windows, or Linux — playback uses each platform's built-in player

## Setup

```bash
./setup.sh          # creates .venv, installs the package (editable) + dev tools, sanity-checks
cp .env.example .env
$EDITOR .env        # paste your OpenAI API key
source .env
```

## Usage

**1. Preprocess the word list.** Extract the dictionary-word lines from the
PDF, strip numbering and parentheticals, and repair ligature glyphs that
`pdftotext` mangles:

```bash
.venv/bin/uil-preprocess --in-file YOUR_LIST.pdf --out-file words.txt
```

**2. Generate speech.** Each word becomes `audio/<index>-<md5>.wav`
(override with `--audio-format`). Existing files are skipped, so re-running
only fills gaps. The script self-throttles to stay under your model's RPM
limit:

```bash
.venv/bin/uil-text-to-speech --in-file words.txt --max-rpm 50
```

**3. Drill.** Each word is spoken `--word-repeat` times with a rest between;
`--range` restricts to a slice of the list (1-based, e.g. `10:50`):

```bash
.venv/bin/uil-play --rest-time 5 --word-repeat 3 --range 10:50
```

## Bringing your own word list

This repo contains **no word lists**. The annual UIL "A+ Spelling" list is a
copyrighted compilation; download your own copy from
[uiltexas.org](https://www.uiltexas.org/academics/dictionary-skills) and pass
it to `preprocess.py`. Any line-oriented word list works — one word per
plain-text line is all `text_to_speech.py` requires.

The current year's list PDF lives at a predictable URL — substitute the
school years you want, e.g. `2025_26` for 2025–26:

```
https://www.uiltexas.org/files/academics/aplus/A+Spelling_2025_26.pdf
```

```bash
curl -fL -o A+Spelling_2025_26.pdf \
  'https://www.uiltexas.org/files/academics/aplus/A+Spelling_2025_26.pdf'
```

Older years follow the same pattern (`A+Spelling_2023_24.pdf`,
`A+Spelling_2024_25.pdf`), though the exact filename has varied slightly
between years — if a URL 404s, check the
[UIL A+ Academics page](https://www.uiltexas.org/academics/dictionary-skills)
for that year's link.

## Repository layout

| Path | Role |
|---|---|
| `pyproject.toml` | package metadata; installs `uil-preprocess`, `uil-text-to-speech`, `uil-play` commands |
| `src/uil_dict_skills/preprocess.py` | PDF → cleaned word list (generator pipeline) |
| `src/uil_dict_skills/text_to_speech.py` | word list → per-word WAV clips via OpenAI TTS |
| `src/uil_dict_skills/play.py` | quiz-mode playback of the audio deck |
| `setup.sh` | venv bootstrap, editable package install, tooling checks |
| `tests/` | pytest suite (runs offline — API and players are faked) |

## Playback

Audio is generated as WAV, the one format every platform plays natively, so
no player binaries are bundled or installed. `play.py` picks the built-in
player for the OS it runs on:

- **macOS** — `afplay`
- **Windows** — PowerShell `Media.SoundPlayer` (`PlaySync`, which blocks so
  the word-repeat/rest pacing works)
- **Linux** — `aplay` (ALSA)

Older decks generated as FLAC still play on macOS via
`python play.py --audio-format flac`.

## Security

Your OpenAI key lives only in `.env` (gitignored); nothing else reads or logs
it. Never commit `.env`. Rotate the key if it ever leaks.

## Development

```bash
.venv/bin/pytest        # run the test suite
```

Tests are fully offline: the OpenAI client and all subprocess calls are
faked, so the suite never touches the network or a player binary.

## License

MIT for everything in this repo (see `LICENSE`). No third-party code or
binaries are included.
