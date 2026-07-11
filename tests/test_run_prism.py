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
# _verify_invocation_directory / the __init__ startup guard
# ------------------------------------------------------------

def test_verify_invocation_directory_wrong_cwd_exits_cleanly(monkeypatch, tmp_path, capsys):
    import run_prism

    monkeypatch.chdir(tmp_path)  # anywhere but src/

    with pytest.raises(SystemExit):
        run_prism._verify_invocation_directory()

    assert 'Please run this script from' in capsys.readouterr().out


def test_verify_invocation_directory_correct_cwd_does_not_exit(monkeypatch):
    import os
    import run_prism

    monkeypatch.chdir(os.path.dirname(os.path.abspath(run_prism.__file__)))

    run_prism._verify_invocation_directory()  # must not raise


def test_init_wrong_cwd_raises_systemexit_not_attributeerror(monkeypatch, tmp_path):
    """Regression test for a fixed bug: the old inline guard called
    self.add_to_transcript(...) before self.mode (and self.logs_dir, which
    add_to_transcript itself reads) were ever set on the instance -- hitting
    it raised AttributeError instead of the intended clean startup error.
    Constructs a real PRISM() (not the __new__-bypassing fixtures used
    elsewhere in this file) specifically to prove __init__ itself now fails
    the right way.
    """
    from run_prism import PRISM

    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        PRISM(mode='test')
