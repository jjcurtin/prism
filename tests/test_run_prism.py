"""Regression test locking in real end-to-end PRISM startup behavior when
the research drive isn't mounted -- e.g. a fresh clone on a machine before
the drive/VPN is set up (see README's Getting Started). Every individual
loader (load_paths/load_api_keys/load_participants/load_task_schedule)
already degrades gracefully (try/except + a warning/error transcript
entry) rather than raising, but that was never exercised at the level of
"does PRISM() actually finish constructing and start serving requests" --
only per-method in test_config_loading.py. This test drives the real
construction sequence (mirroring what __init__ does) against an
environment where the drive directory doesn't exist at all, so a future
change can't silently reintroduce a hard crash on a missing drive.
"""
import pytest


@pytest.fixture
def fake_prism_env_no_drive(tmp_path):
    """A repo checkout with no research drive present whatsoever (the
    drive_mount_posix path itself doesn't exist) -- unlike fake_prism_env,
    which builds a full fake drive."""
    repo_root = tmp_path / 'repo'
    drive_root = tmp_path / 'drive'  # deliberately never created

    (repo_root / 'config').mkdir(parents=True)
    (repo_root / 'config' / 'repo_paths.csv').write_text(
        '"key","value"\n'
        '"logs_dir","logs"\n'
        f'"drive_mount_windows","{drive_root}"\n'
        f'"drive_mount_posix","{drive_root}"\n'
        '"prism_drive_subpath","optimize/prism"\n'
    )
    (repo_root / 'environment').write_text('dev')
    return repo_root


@pytest.fixture
def booted_prism_no_drive(fake_prism_env_no_drive):
    """Drives the real PRISM()-construction sequence (paths, API keys,
    both task managers, Flask app) against fake_prism_env_no_drive --
    bypassing only __init__ itself (same convention as the `prism_instance`
    fixture in conftest.py), since __init__ can't be pointed at a fake
    repo_root directly, and replacing launch_web_app's blocking
    waitress `serve()` call with building the Flask app in-process so the
    test can hit it via test_client() instead of a real socket.
    """
    from run_prism import PRISM
    from task_managers._system_task_manager import SystemTaskManager
    from task_managers._participant_manager import ParticipantManager

    p = PRISM.__new__(PRISM)
    p.mode = 'test'
    p.repo_root = fake_prism_env_no_drive
    p.load_paths()
    p.load_api_keys()
    p.system_task_manager = SystemTaskManager(p)
    p.participant_manager = ParticipantManager(p)
    try:
        yield p
    finally:
        # Both managers start a non-daemon polling thread (_task_manager.py)
        # that never exits on its own -- stop() joins it. Without this the
        # test process itself would hang forever after the test body finishes.
        p.system_task_manager.stop()
        p.participant_manager.stop()


def test_prism_boots_when_research_drive_is_unmounted(booted_prism_no_drive):
    p = booted_prism_no_drive

    assert p.system_task_manager.tasks == []
    assert p.participant_manager.participants == []
    assert not hasattr(p, 'twilio_account_sid')
    assert not hasattr(p, 'participants_path')


def test_prism_still_serves_requests_when_research_drive_is_unmounted(booted_prism_no_drive):
    from _routes import create_flask_app

    p = booted_prism_no_drive
    p.start_time = __import__('datetime').datetime.now()
    client = create_flask_app(p).test_client()

    ok = client.get('/system/get_mode')
    assert ok.status_code == 200
    assert ok.get_json() == {'mode': 'test'}

    # Nothing loaded (no participants.csv/schedule found with the drive
    # unmounted) is a legitimately empty result, not a request failure --
    # these routes now return 200 with an empty list rather than 404,
    # same fix as the empty-vs-error routes tests elsewhere.
    degraded = client.get('/participants/get_participants')
    assert degraded.status_code == 200
    assert degraded.get_json() == {'participants': []}

    degraded_tasks = client.get('/system/get_task_schedule')
    assert degraded_tasks.status_code == 200
    assert degraded_tasks.get_json() == {'tasks': []}


# ------------------------------------------------------------
# cwd independence: __init__ has no startup-directory guard
# ------------------------------------------------------------
#
# There used to be one, in two versions: the original compared __file__'s
# fixed on-disk location (could never actually fail, regardless of
# invocation cwd -- a no-op that happened to never fire), and a later
# replacement did a real os.getcwd() check -- which DID fire, and broke
# `python src/run_prism.py` run from the repo root, a previously-working
# (if only by the first version's accident) invocation style. Removed
# entirely: cwd genuinely doesn't matter here (sys.path[0] is the script's
# own directory regardless of launch cwd; every path this app touches is
# repo_root/drive-anchored, never cwd-relative).
#
# This test deliberately reuses fake_prism_env_no_drive (drive_root never
# created) rather than pointing at the real repo's config/repo_paths.csv --
# that file's real drive_mount_posix (/mnt/research_drive) can hang for a
# long time off-VPN (the exact slow-automount hazard check_research_drive()
# elsewhere in this codebase already works around with a timeout;
# load_paths()/load_api_keys() have no equivalent protection), which would
# make this test flaky/slow specifically in the environment that most needs
# to run it quickly (CI, or a laptop off VPN). A nonexistent *local* path
# fails instantly with FileNotFoundError instead.

def test_no_startup_directory_guard_exists():
    """Direct regression test for the removal itself: locks in that
    _verify_invocation_directory (and any equivalent check) is gone from
    the module, not just that its old effects don't manifest -- so a
    future change can't silently reintroduce it under a new name without
    this test being touched.
    """
    import run_prism

    assert not hasattr(run_prism, '_verify_invocation_directory')


# ------------------------------------------------------------
# _unlink_pid_file_if_owned -- ownership-checked shutdown unlink
# ------------------------------------------------------------
#
# Regression tests for a bug found by an external adversarial review of the
# double-launch scenario: handle_shutdown() used to unlink() the PID file
# unconditionally. A second instance launched while a first was still
# running clobbers the first's PID file at write time (_write_pid_file has
# no liveness check yet -- see the B4b fix); if that second instance later
# receives SIGTERM, its old unconditional unlink would delete a file that
# had already stopped being "its" file, leaving the ORIGINAL still-live
# instance with no PID file at all.

def _make_bare_prism(repo_root):
    from run_prism import PRISM
    p = PRISM.__new__(PRISM)
    p.repo_root = repo_root
    p.mode = 'test'
    p.logs_dir = str(repo_root / 'logs')
    return p


def test_unlink_pid_file_if_owned_removes_its_own_pid(tmp_path):
    import os
    from run_prism import PID_FILE_NAME

    p = _make_bare_prism(tmp_path)
    pid_file = tmp_path / PID_FILE_NAME
    pid_file.write_text(str(os.getpid()))

    p._unlink_pid_file_if_owned()

    assert not pid_file.exists()


def test_unlink_pid_file_if_owned_leaves_a_mismatched_pid_file(tmp_path):
    import os
    from run_prism import PID_FILE_NAME

    p = _make_bare_prism(tmp_path)
    pid_file = tmp_path / PID_FILE_NAME
    other_pid = os.getpid() + 1  # guaranteed not to be this test process
    pid_file.write_text(str(other_pid))

    p._unlink_pid_file_if_owned()

    assert pid_file.exists()
    assert pid_file.read_text() == str(other_pid)
    transcript_text = (tmp_path / 'logs' / 'transcripts' / 'test_transcript.txt').read_text()
    assert 'WARNING' in transcript_text and str(other_pid) in transcript_text


def test_unlink_pid_file_if_owned_tolerates_a_missing_file(tmp_path):
    p = _make_bare_prism(tmp_path)

    p._unlink_pid_file_if_owned()  # must not raise


def test_init_succeeds_regardless_of_invocation_directory(monkeypatch, fake_prism_env_no_drive):
    import os
    from run_prism import PRISM
    from task_managers._system_task_manager import SystemTaskManager
    from task_managers._participant_manager import ParticipantManager

    original_cwd = os.getcwd()
    real_repo_root = original_cwd  # this test file's own cwd at collection time
    try:
        for cwd in (fake_prism_env_no_drive, fake_prism_env_no_drive / 'config'):
            monkeypatch.chdir(cwd)
            # Mirrors booted_prism_no_drive's construction sequence (__init__
            # can't be pointed at a fake repo_root directly), but repeated
            # per-cwd to prove the outcome doesn't depend on it.
            p = PRISM.__new__(PRISM)
            p.mode = 'test'
            p.repo_root = fake_prism_env_no_drive
            p.load_paths()  # must not raise regardless of cwd
            p.load_api_keys()
            p.system_task_manager = SystemTaskManager(p)
            p.participant_manager = ParticipantManager(p)
            p.system_task_manager.stop()
            p.participant_manager.stop()
    finally:
        os.chdir(real_repo_root)


# ------------------------------------------------------------
# _pid_is_alive / _acquire_pid_file -- refuse a double launch
# ------------------------------------------------------------
#
# Regression tests for the actual fix to the zombie-manager-threads bug: a
# second launch used to just overwrite the PID file and construct
# everything (managers included) regardless of whether a first instance
# was still running. Verified directly (see the plan/commit message) that
# a non-daemon background thread survives an uncaught exception in the
# main thread -- so once launch_web_app() fails on the port-already-bound
# second launch, its manager threads kept running headless, fully loaded
# with the schedule. Refusing to construct the managers at all, here,
# closes that off for the common case (two launches of the same instance).

def test_pid_is_alive_true_for_the_current_process():
    import os
    from run_prism import _pid_is_alive

    assert _pid_is_alive(os.getpid()) is True


def test_pid_is_alive_false_for_a_dead_pid():
    import subprocess
    import sys
    from run_prism import _pid_is_alive

    proc = subprocess.Popen([sys.executable, '-c', 'pass'])
    proc.wait(timeout=5)

    assert _pid_is_alive(proc.pid) is False


def test_acquire_pid_file_refuses_to_start_when_a_live_pid_is_recorded(tmp_path):
    import os
    import pytest
    from run_prism import PID_FILE_NAME

    p = _make_bare_prism(tmp_path)
    pid_file = tmp_path / PID_FILE_NAME
    pid_file.write_text(str(os.getpid()))  # this test process is definitely alive

    with pytest.raises(SystemExit):
        p._acquire_pid_file()

    # Refused before overwriting -- the file must still name the "other"
    # (in this test, coincidentally the same, but unmodified) live process,
    # not silently get replaced on the way to refusing.
    assert pid_file.read_text() == str(os.getpid())
    transcript_text = (tmp_path / 'logs' / 'transcripts' / 'test_transcript.txt').read_text()
    assert 'Refusing to start' in transcript_text


def test_acquire_pid_file_overwrites_a_stale_pid_and_warns(tmp_path):
    import subprocess
    import sys
    from run_prism import PID_FILE_NAME

    proc = subprocess.Popen([sys.executable, '-c', 'pass'])
    proc.wait(timeout=5)

    p = _make_bare_prism(tmp_path)
    pid_file = tmp_path / PID_FILE_NAME
    pid_file.write_text(str(proc.pid))

    p._acquire_pid_file()  # must not raise -- stale, not live

    import os
    assert pid_file.read_text() == str(os.getpid())
    transcript_text = (tmp_path / 'logs' / 'transcripts' / 'test_transcript.txt').read_text()
    assert 'no-longer-running' in transcript_text


def test_acquire_pid_file_writes_fresh_when_no_file_exists(tmp_path):
    import os
    from run_prism import PID_FILE_NAME

    p = _make_bare_prism(tmp_path)
    pid_file = tmp_path / PID_FILE_NAME
    assert not pid_file.exists()

    p._acquire_pid_file()  # must not raise

    assert pid_file.read_text() == str(os.getpid())


# ------------------------------------------------------------
# _launch_web_app_or_shutdown -- defense in depth if the port bind fails
# ------------------------------------------------------------
#
# Regression test for the other half of the zombie-manager-threads bug:
# _acquire_pid_file (previous commit) closes the common case (two launches
# of the same PRISM instance), but an exception escaping launch_web_app()
# for any OTHER reason (e.g. a port already held by an unrelated process)
# used to just kill the main thread while the two non-daemon manager
# threads -- already fully loaded with the schedule -- kept running
# headless. os._exit is monkeypatched here specifically so this test can
# drive handle_shutdown's real code path without actually terminating the
# test process.

def test_launch_web_app_or_shutdown_stops_managers_and_exits_on_failure(monkeypatch, tmp_path):
    import os
    from run_prism import PRISM

    p = _make_bare_prism(tmp_path)
    p.launch_web_app = lambda: (_ for _ in ()).throw(OSError('Address already in use'))

    stopped = {'system': False, 'participant': False}

    class FakeManager:
        def __init__(self, key):
            self.key = key

        def stop(self):
            stopped[self.key] = True

    p.system_task_manager = FakeManager('system')
    p.participant_manager = FakeManager('participant')
    exit_codes = []
    monkeypatch.setattr(os, '_exit', lambda code=0: exit_codes.append(code))

    p._launch_web_app_or_shutdown()

    assert stopped == {'system': True, 'participant': True}
    assert exit_codes == [0]
    transcript_text = (tmp_path / 'logs' / 'transcripts' / 'test_transcript.txt').read_text()
    assert 'Web server failed to start or crashed' in transcript_text
    assert 'shutting down task managers' in transcript_text


def test_launch_web_app_or_shutdown_does_not_intervene_on_success(tmp_path):
    p = _make_bare_prism(tmp_path)
    calls = []
    p.launch_web_app = lambda: calls.append('called')

    p._launch_web_app_or_shutdown()  # must not raise, must not shut anything down

    assert calls == ['called']
