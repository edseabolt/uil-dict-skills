#! /usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
    echo 'created .venv'
fi

.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo 'dependencies installed'

if ! command -v pdftotext >/dev/null 2>&1; then
    echo 'warning: pdftotext not found — install poppler (see README.md)' >&2
fi

if [ ! -f .env ]; then
    echo "warning: .env missing — run: cp .env.example .env, then paste your OpenAI API key" >&2
fi

case "$(uname -s)" in
    Darwin)
        command -v afplay >/dev/null 2>&1 || echo 'warning: afplay not found — playback will fail' >&2
        ;;
    Linux)
        command -v aplay >/dev/null 2>&1 || echo 'warning: aplay not found — playback will fail' >&2
        ;;
    MINGW*|MSYS*|CYGWIN*)
        command -v powershell >/dev/null 2>&1 || echo 'warning: powershell not found — playback will fail' >&2
        ;;
esac

echo 'done. see README.md for the preprocess -> text_to_speech -> play workflow.'
