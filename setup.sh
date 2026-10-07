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
    echo "warning: pdftotext not found (install poppler: 'brew install poppler')" >&2
fi

if [ ! -f .env ]; then
    echo "warning: .env missing — run: cp .env.example .env, then paste your OpenAI API key" >&2
fi

if [ ! -x fmedia/darwin/fmedia ] && [ ! -x fmedia/windows/fmedia.exe ]; then
    echo 'warning: no fmedia player found under fmedia/ — playback will fail' >&2
fi

echo 'done. see README.md for the preprocess -> text_to_speech -> play workflow.'
