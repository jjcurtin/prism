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
        '"drive_mount_windows","S:"\n'
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

    degraded = client.get('/participants/get_participants')
    assert degraded.status_code == 404
    assert 'error' in degraded.get_json()

    degraded_tasks = client.get('/system/get_task_schedule')
    assert degraded_tasks.status_code == 404
    assert 'error' in degraded_tasks.get_json()
