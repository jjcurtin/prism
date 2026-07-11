"""Tests for the repo-root stop_server.py script -- not part of src/, so it
needs its own sys.path setup (tests/conftest.py only adds src/).
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import stop_server


def _skip_sleep(monkeypatch):
    """main()'s trailing time.sleep(1) is real startup-settling time for a
    real server process -- irrelevant and just slows the suite down when
    these tests target a fake/no-op process instead."""
    monkeypatch.setattr(stop_server.time, 'sleep', lambda seconds: None)


def test_stop_via_pid_file_kills_the_recorded_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(stop_server, 'PID_FILE', tmp_path / '.run_prism.pid')
    _skip_sleep(monkeypatch)
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    stop_server.PID_FILE.write_text(str(proc.pid))

    stop_server.main()

    proc.wait(timeout=5)
    assert proc.returncode is not None  # the process actually exited
    assert not stop_server.PID_FILE.exists()


def test_stop_via_pid_file_missing_falls_back_to_pattern_match(tmp_path, monkeypatch):
    monkeypatch.setattr(stop_server, 'PID_FILE', tmp_path / '.run_prism.pid')
    _skip_sleep(monkeypatch)
    called = {}

    def fake_pattern_match():
        called['ran'] = True

    monkeypatch.setattr(stop_server, '_stop_via_pattern_match', fake_pattern_match)

    stop_server.main()

    assert called.get('ran') is True


def test_stop_via_pid_file_stale_pid_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(stop_server, 'PID_FILE', tmp_path / '.run_prism.pid')
    _skip_sleep(monkeypatch)
    # A pid that (overwhelmingly likely) doesn't correspond to any real
    # process on this machine.
    stop_server.PID_FILE.write_text('999999')

    stop_server.main()  # must not raise

    assert not stop_server.PID_FILE.exists()


def test_stop_via_pid_file_returns_false_when_no_pid_file(tmp_path, monkeypatch):
    monkeypatch.setattr(stop_server, 'PID_FILE', tmp_path / '.run_prism.pid')

    assert stop_server._stop_via_pid_file() is False
