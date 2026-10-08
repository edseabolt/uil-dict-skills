"""Tests for play.py: range parsing, ordering, player resolution, drill loop.

All tests run offline: subprocess.run is faked so no player binary is
launched, and audio decks are synthesized in temporary directories.
"""

import logging
from pathlib import Path

import pytest

import uil_dict_skills.play as play


def make_run_recorder(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Replace subprocess.run with a recorder and return its call log.

    Args:
        monkeypatch: Swaps the real subprocess.run for the recorder.

    Returns:
        The list of argv lists passed to each fake invocation.
    """
    calls: list[list[str]] = []

    class Result:
        """Stand-in for subprocess.CompletedProcess.

        Carries stdout/stderr because the patch replaces the global
        subprocess.run — anything else that shells out through it
        (e.g. platform.system() on Windows/Python 3.10) gets this
        object back and expects the CompletedProcess surface.
        """

        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

        def check_returncode(self) -> None:
            """Simulate a successful player invocation."""

    def fake_run(argv: list[str], **kwargs: object) -> Result:
        calls.append(argv)
        return Result()

    monkeypatch.setattr(play.subprocess, "run", fake_run)
    return calls


def test_parse_range_full_slice() -> None:
    """Convert a bounded "10:50" range to 0-based inclusive-exclusive bounds."""
    assert play.parse_range("10:50", 100) == (9, 50)


def test_parse_range_open_start() -> None:
    """Treat an empty start as the beginning of the list."""
    assert play.parse_range(":50", 100) == (0, 50)


def test_parse_range_open_end() -> None:
    """Treat an empty end as the end of the list."""
    assert play.parse_range("10:", 100) == (9, 100)


def test_parse_range_clamps_out_of_bounds() -> None:
    """Clamp both bounds into [0, total]."""
    assert play.parse_range("0:200", 100) == (0, 100)


def test_parse_range_reversed_yields_empty_slice() -> None:
    """Produce an empty (not crashing) selection for start > end."""
    start, end = play.parse_range("50:10", 100)
    assert list(range(100)[start:end]) == []


def test_sort_key_orders_index_prefix_numerically() -> None:
    """Sort by the numeric index prefix, not lexicographically."""
    files = ["10-a.wav", "2-b.wav", "1-c.wav"]
    assert sorted(files, key=play.sort_key) == ["1-c.wav", "2-b.wav", "10-a.wav"]


def test_collect_audio_files_filters_by_format(tmp_path: Path) -> None:
    """Return only clips matching the requested format, in index order.

    Args:
        tmp_path: Temporary directory standing in for audio/.
    """
    for name in ("2-b.wav", "1-c.wav", "3-d.flac", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    assert play.collect_audio_files(str(tmp_path), "wav") == ["1-c.wav", "2-b.wav"]


def test_resolve_play_cmd_darwin() -> None:
    """Use the built-in afplay on macOS."""
    assert play.resolve_play_cmd("darwin", "a.wav") == ["afplay", "a.wav"]


def test_resolve_play_cmd_linux() -> None:
    """Use the built-in aplay in quiet mode on Linux."""
    assert play.resolve_play_cmd("linux", "a.wav") == ["aplay", "-q", "a.wav"]


def test_resolve_play_cmd_windows_escapes_apostrophe() -> None:
    """Escape single quotes in paths embedded into the PowerShell script."""
    argv = play.resolve_play_cmd("windows", "it's.wav")
    assert argv is not None
    assert argv[0] == "powershell"
    assert "it''s.wav" in argv[-1]


def test_resolve_play_cmd_unsupported_returns_none() -> None:
    """Report unsupported platforms as None rather than raising."""
    assert play.resolve_play_cmd("sunos", "a.wav") is None


def test_main_without_audio_dir_logs_error_and_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Log a clear error instead of raising on a fresh clone with no audio/.

    Args:
        tmp_path: Empty temporary directory (cwd) without audio/.
        monkeypatch: Sets the CLI arguments.
        caplog: Captures the error-level log record.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["play.py"])
    with caplog.at_level(logging.ERROR):
        play.main()
    assert "not found" in caplog.text


def test_main_plays_each_clip_word_repeat_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Play every selected clip exactly --word-repeat times.

    Args:
        tmp_path: Temporary directory providing a two-clip audio/ deck.
        monkeypatch: Sets CLI flags and fakes subprocess.run.
    """
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "1-a.wav").write_bytes(b"x")
    (tmp_path / "audio" / "2-b.wav").write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["play.py", "--no-random", "--word-repeat", "3", "--rest-time", "0"]
    )
    calls = make_run_recorder(monkeypatch)
    play.main()
    assert len(calls) == 6  # 2 clips x 3 repeats


def test_main_range_slice_selects_subset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Restrict playback to the clips selected by --range.

    Args:
        tmp_path: Temporary directory providing a three-clip audio/ deck.
        monkeypatch: Sets CLI flags and fakes subprocess.run.
    """
    audio = tmp_path / "audio"
    audio.mkdir()
    for i in (1, 2, 3):
        (audio / f"{i}-w{i}.wav").write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["play.py", "--no-random", "--word-repeat", "1", "--rest-time", "0", "--range", "2:3"],
    )
    calls = make_run_recorder(monkeypatch)
    play.main()
    # The player command wraps the clip path differently per platform
    # (bare path on macOS/Linux, embedded in a PowerShell script on
    # Windows), so extract clips by membership rather than position.
    clip_names = {f"{i}-w{i}.wav" for i in (1, 2, 3)}
    played = [name for argv in calls for arg in argv for name in clip_names if name in arg]
    assert played == ["2-w2.wav", "3-w3.wav"]
