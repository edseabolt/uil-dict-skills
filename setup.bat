@echo off
rem Bootstrap: create venv, install the package + dev tools, sanity-check.
rem Windows equivalent of setup.sh. Run from the repo root: setup.bat
cd /d "%~dp0"

if not exist .venv (
    python -m venv .venv
    echo created .venv
)

.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -e ".[dev]"
echo dependencies installed

where pdftotext >nul 2>&1
if errorlevel 1 echo warning: pdftotext not found - install poppler for Windows, see README.md 1>&2

if not exist .env echo warning: .env missing - copy .env.example to .env, then paste your OpenAI API key 1>&2

where powershell >nul 2>&1
if errorlevel 1 echo warning: powershell not found - playback will fail 1>&2

echo done. installed: uil-preprocess, uil-text-to-speech, uil-play plus pytest.
echo see README.md for the preprocess -^> text_to_speech -^> play workflow.
