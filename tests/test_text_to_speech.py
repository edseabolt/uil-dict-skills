"""Tests for text_to_speech.py (offline — the OpenAI client is faked)."""

import hashlib

import uil_dict_skills.text_to_speech as tts


def test_clip_filename_prefixes_one_based_index():
    assert tts.clip_filename(0, "word", "wav") == f'1-{hashlib.md5(b"word").hexdigest()}.wav'


def test_clip_filename_md5_is_stable_across_calls():
    assert tts.clip_filename(5, "same", "wav") == tts.clip_filename(5, "same", "wav")


def test_clip_filename_honors_audio_format():
    name = tts.clip_filename(0, "word", "flac")
    assert name.endswith(".flac")


class FakeResponse:
    def __init__(self):
        self.written_to = None

    def stream_to_file(self, path):
        self.written_to = path
        with open(path, "wb") as f:
            f.write(b"fake audio")


class FakeSpeech:
    def __init__(self):
        self.calls = []
        self._response = FakeResponse()

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class FakeAudio:
    def __init__(self):
        self.speech = FakeSpeech()


class FakeClient:
    instances = []

    def __init__(self, max_retries=0):
        self.audio = FakeAudio()
        FakeClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_main_skips_existing_clips_and_fakes_client(tmp_path, monkeypatch):
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
