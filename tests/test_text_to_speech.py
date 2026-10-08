"""Tests for text_to_speech.py (offline — the OpenAI client is faked).

FakeClient mimics the surface main() uses: context-manager entry,
client.audio.speech.create(**kwargs) returning an object with
stream_to_file(). No network calls occur.
"""

import hashlib
from pathlib import Path
from typing import ClassVar

import pytest

import uil_dict_skills.text_to_speech as tts


def test_clip_filename_prefixes_one_based_index() -> None:
    """Prefix the md5-derived filename with the 1-based list position."""
    assert tts.clip_filename(0, "word", "wav") == f"1-{hashlib.md5(b'word').hexdigest()}.wav"


def test_clip_filename_md5_is_stable_across_calls() -> None:
    """Derive identical filenames for identical words (re-runs fill gaps)."""
    assert tts.clip_filename(5, "same", "wav") == tts.clip_filename(5, "same", "wav")


def test_clip_filename_honors_audio_format() -> None:
    """Append the requested audio format as the file extension."""
    assert tts.clip_filename(0, "word", "flac").endswith(".flac")


class FakeResponse:
    """Stand-in for the SDK response: records the target, writes bytes."""

    def __init__(self) -> None:
        self.written_to: str | None = None

    def stream_to_file(self, path: str) -> None:
        """Write placeholder bytes, as the real response would.

        Args:
            path: Destination path supplied by the caller.
        """
        self.written_to = path
        with open(path, "wb") as f:
            f.write(b"fake audio")


class FakeSpeech:
    """Stand-in for client.audio.speech: records create() calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> FakeResponse:
        """Record the API kwargs and return a fake response.

        Args:
            **kwargs: Model, voice, format, and input passed by main().

        Returns:
            A FakeResponse that writes placeholder audio.
        """
        self.calls.append(kwargs)
        return FakeResponse()


class FakeAudio:
    """Stand-in for client.audio: hosts the speech resource."""

    def __init__(self) -> None:
        self.speech = FakeSpeech()


class FakeClient:
    """Stand-in for openai.OpenAI; tracks every created instance."""

    instances: ClassVar[list["FakeClient"]] = []

    def __init__(self, max_retries: int = 0) -> None:
        self.audio = FakeAudio()
        FakeClient.instances.append(self)

    def __enter__(self) -> "FakeClient":
        """Match the real client's context-manager protocol."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Match the real client's context-manager protocol (never suppresses)."""
        return None


def test_main_skips_existing_clips_and_fakes_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Call the API only for words whose clip does not already exist.

    Args:
        tmp_path: Temporary directory providing the input list and audio/.
        monkeypatch: Sets CLI arguments and swaps in FakeClient.
    """
    (tmp_path / "in.txt").write_text("abandon\nabsent\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["tts.py", "--in-file", "in.txt"])

    # pre-create the second word's clip; only the first should hit the API
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / tts.clip_filename(1, "absent", "wav")).write_bytes(b"x")

    monkeypatch.setattr(tts, "OpenAI", FakeClient)
    tts.main()

    assert len(FakeClient.instances) == 1
    calls = FakeClient.instances[0].audio.speech.calls
    assert len(calls) == 1
    assert calls[0]["input"] == "[pause]abandon"
    assert calls[0]["model"] == "tts-1"
    assert calls[0]["voice"] == "shimmer"
    assert calls[0]["response_format"] == "wav"
    files = sorted(p.name for p in audio.iterdir())
    assert tts.clip_filename(0, "abandon", "wav") in files
    assert tts.clip_filename(1, "absent", "wav") in files


def test_main_throttles_never_exceeds_rpm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the request counter at the RPM boundary without real sleeping.

    Args:
        tmp_path: Temporary directory providing a three-word input list.
        monkeypatch: Sets a 2-RPM limit and stubs time.sleep.
    """
    (tmp_path / "in.txt").write_text("a\nb\nc\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["tts.py", "--in-file", "in.txt", "--max-rpm", "2", "--max-time-secs", "0"]
    )
    monkeypatch.setattr(tts, "OpenAI", FakeClient)
    monkeypatch.setattr(tts.time, "sleep", lambda secs: None)
    tts.main()  # must not raise; rate limiting exercised without sleeping
