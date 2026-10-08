"""Tests for play.py: range parsing, ordering, player resolution, drill loop."""

import logging

import pytest

import uil_dict_skills.play as play


def make_run_recorder(monkeypatch):
    calls = []

    class Result:
        def check_returncode(self):
            pass

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return Result()

    monkeypatch.setattr(play.subprocess, 'run', fake_run)
    return calls


def test_parse_range_full_slice():
    assert play.parse_range('10:50', 100) == (9, 50)


def test_parse_range_open_start():
    assert play.parse_range(':50', 100) == (0, 50)


def test_parse_range_open_end():
    assert play.parse_range('10:', 100) == (9, 100)


def test_parse_range_clamps_out_of_bounds():
    assert play.parse_range('0:200', 100) == (0, 100)


def test_parse_range_reversed_yields_empty_slice():
    start, end = play.parse_range('50:10', 100)
    assert list(range(100)[start:end]) == []


def test_sort_key_orders_index_prefix_numerically():
    files = ['10-a.wav', '2-b.wav', '1-c.wav']
    assert sorted(files, key=play.sort_key) == ['1-c.wav', '2-b.wav', '10-a.wav']


def test_collect_audio_files_filters_by_format(tmp_path):
    for name in ('2-b.wav', '1-c.wav', '3-d.flac', 'notes.txt'):
        (tmp_path / name).write_bytes(b'x')
    assert play.collect_audio_files(str(tmp_path), 'wav') == ['1-c.wav', '2-b.wav']


def test_resolve_play_cmd_darwin():
    assert play.resolve_play_cmd('darwin', 'a.wav') == ['afplay', 'a.wav']


def test_resolve_play_cmd_linux():
    assert play.resolve_play_cmd('linux', 'a.wav') == ['aplay', '-q', 'a.wav']


def test_resolve_play_cmd_windows_escapes_apostrophe():
    argv = play.resolve_play_cmd('windows', "it's.wav")
    assert argv[0] == 'powershell'
    assert "it''s.wav" in argv[-1]


def test_resolve_play_cmd_unsupported_returns_none():
    assert play.resolve_play_cmd('sunos', 'a.wav') is None


def test_main_without_audio_dir_logs_error_and_exits(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('sys.argv', ['play.py'])
    with caplog.at_level(logging.ERROR):
        play.main()
    assert 'not found' in caplog.text


def test_main_plays_each_clip_word_repeat_times(tmp_path, monkeypatch):
    (tmp_path / 'audio').mkdir()
    (tmp_path / 'audio' / '1-a.wav').write_bytes(b'x')
    (tmp_path / 'audio' / '2-b.wav').write_bytes(b'x')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('sys.argv', [
        'play.py', '--no-random', '--word-repeat', '3', '--rest-time', '0'])
    calls = make_run_recorder(monkeypatch)
    play.main()
    assert len(calls) == 6  # 2 clips x 3 repeats


def test_main_range_slice_selects_subset(tmp_path, monkeypatch):
    audio = tmp_path / 'audio'
    audio.mkdir()
    for i in (1, 2, 3):
        (audio / f'{i}-w{i}.wav').write_bytes(b'x')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('sys.argv', [
        'play.py', '--no-random', '--word-repeat', '1', '--rest-time', '0',
        '--range', '2:3'])
    calls = make_run_recorder(monkeypatch)
    play.main()
    played = [argv[-1].split('/')[-1].split('\\')[-1] for argv in calls]
    assert played == ['2-w2.wav', '3-w3.wav']
