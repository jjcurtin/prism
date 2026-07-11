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


def test_stop_via_pid_file_failed_kill_does_not_unlink_pid_file(tmp_path, monkeypatch):
    """Regression test for a real bug (external adversarial review,
    confirmed via a standalone repro of Python's finally-block ordering
    semantics): the old `finally: PID_FILE.unlink(missing_ok=True)` ran
    even when the kill itself failed (e.g. PermissionError, if this script
    runs as a different user than the one that started run_prism.py) --
    deleting the PID file on a FAILED stop. The next launch would then see
    no PID file, believe nothing was running, and start a second live
    instance alongside the still-running first one -- silently recreating
    the exact double-launch scenario _acquire_pid_file() exists to
    prevent.
    """
    monkeypatch.setattr(stop_server, 'PID_FILE', tmp_path / '.run_prism.pid')
    stop_server.PID_FILE.write_text('12345')

    def raise_permission_error(pid, sig):
        raise PermissionError("kill not permitted")

    monkeypatch.setattr(stop_server.os, 'kill', raise_permission_error)

    result = stop_server._stop_via_pid_file()

    assert result is False
    assert stop_server.PID_FILE.exists()  # NOT deleted -- the kill failed


def test_stop_via_pid_file_returns_false_when_no_pid_file(tmp_path, monkeypatch):
    monkeypatch.setattr(stop_server, 'PID_FILE', tmp_path / '.run_prism.pid')

    assert stop_server._stop_via_pid_file() is False


# ------------------------------------------------------------
# _stop_via_pattern_match -- reports candidates, never kills
# ------------------------------------------------------------
#
# Regression tests for a bug found by an external adversarial review,
# demonstrated live killing unrelated bystander processes (four separate
# times, including the operator's own shell): the old fallback ran
# `pkill -f run_prism.py`, a substring match against every process's full
# command line -- it can't distinguish the real PRISM server from
# anything else whose argv happens to contain that string.

def test_pattern_match_fallback_reports_a_decoy_without_killing_it():
    # A real process whose command line contains "run_prism.py" -- the
    # exact shape the old pkill -f would have matched and killed.
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)', 'run_prism.py'])
    try:
        import time as time_module
        time_module.sleep(0.3)  # let it actually start before pgrep looks

        found = stop_server._stop_via_pattern_match()

        assert found is True
        assert proc.poll() is None  # still alive -- NOT killed
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_pattern_match_fallback_returns_false_when_nothing_matches(monkeypatch):
    class _EmptyResult:
        stdout = ''

    monkeypatch.setattr(stop_server.subprocess, 'run', lambda *a, **k: _EmptyResult())

    assert stop_server._stop_via_pattern_match() is False


def test_main_exits_nonzero_when_fallback_finds_unstoppable_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(stop_server, 'PID_FILE', tmp_path / '.run_prism.pid')
    _skip_sleep(monkeypatch)
    monkeypatch.setattr(stop_server, '_stop_via_pattern_match', lambda: True)

    assert stop_server.main() == 1


def test_main_exits_zero_when_fallback_finds_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(stop_server, 'PID_FILE', tmp_path / '.run_prism.pid')
    _skip_sleep(monkeypatch)
    monkeypatch.setattr(stop_server, '_stop_via_pattern_match', lambda: False)

    assert stop_server.main() == 0


def test_main_exits_zero_when_pid_file_path_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(stop_server, 'PID_FILE', tmp_path / '.run_prism.pid')
    _skip_sleep(monkeypatch)
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    stop_server.PID_FILE.write_text(str(proc.pid))

    assert stop_server.main() == 0

    proc.wait(timeout=5)
