from unittest.mock import MagicMock

from system_tasks._check_system import CheckSystem


def test_run_only_checks_live_system_state_not_static_files(fake_app, monkeypatch, tmp_path):
    """Regression test for a fixed bug: CHECK_SYSTEM used to also run
    check_file_system, a static local directory/file existence check
    (../data, ../scripts, ../logs, hardcoded cwd-relative) that's a
    deployment-verification concern, not a runtime diagnostic -- it failed
    in practice with "The '../scripts' directory is missing" on a
    perfectly healthy system just because cwd wasn't exactly src/. run()
    now only checks things that reflect live system state: the research
    drive connection, Rscript's availability on PATH, loaded-participant
    data integrity, and reminders.csv's readability/schema. Deliberately
    doesn't touch the filesystem for the first three (no fake src/ tree, no
    chdir) to prove run() no longer depends on it for those -- reminders.csv
    is a real runtime dependency, so it does get a real (valid) file here.
    shutil.which is mocked so this doesn't depend on whether R actually
    happens to be installed on whatever machine runs the test suite.
    """
    fake_app.mode = 'test'
    fake_app.participant_manager = MagicMock()
    fake_app.participant_manager.get_participants.return_value = []
    reminders_file = tmp_path / 'reminders.csv'
    reminders_file.write_text('subid,unique_id,on_study,remind_ema,remind_feedback\n')
    fake_app.reminders_path = str(reminders_file)
    monkeypatch.setattr('system_tasks._check_system.shutil.which', lambda name: '/usr/bin/Rscript')

    result = CheckSystem(fake_app).run()

    assert result == 0
    assert not any('directory is missing' in msg for _, msg in fake_app.transcript)
    assert not any('file' in msg.lower() and 'missing' in msg.lower() for _, msg in fake_app.transcript)


def test_check_rscript_available_found_returns_0(fake_app, monkeypatch):
    monkeypatch.setattr('system_tasks._check_system.shutil.which', lambda name: '/usr/bin/Rscript')

    result = CheckSystem(fake_app).check_rscript_available()

    assert result == 0
    assert not any(level == 'ERROR' for level, _ in fake_app.transcript)


def test_check_rscript_available_missing_returns_1_and_errors(fake_app, monkeypatch):
    monkeypatch.setattr('system_tasks._check_system.shutil.which', lambda name: None)

    result = CheckSystem(fake_app).check_rscript_available()

    assert result == 1
    assert any(
        'Rscript executable not found on PATH' in msg and 'Is R installed' in msg
        for _, msg in fake_app.transcript
    )


def test_check_research_drive_skipped_in_test_mode(fake_app):
    fake_app.mode = 'test'

    result = CheckSystem(fake_app).check_research_drive()

    assert result == 0
    assert fake_app.transcript == []


def test_check_research_drive_prod_mode_mounted_and_listable_returns_0(tmp_path, fake_app):
    fake_app.mode = 'prod'
    drive_mount = tmp_path / 'drive'
    drive_mount.mkdir()
    fake_app.drive_mount = str(drive_mount)

    result = CheckSystem(fake_app).check_research_drive()

    assert result == 0
    assert any('Successfully connected to Research Drive' in msg for _, msg in fake_app.transcript)


def test_check_research_drive_prod_mode_missing_mount_returns_1(tmp_path, fake_app):
    fake_app.mode = 'prod'
    fake_app.drive_mount = str(tmp_path / 'not_actually_mounted')

    result = CheckSystem(fake_app).check_research_drive()

    assert result == 1
    assert any('Failed to connect to Research Drive' in msg for _, msg in fake_app.transcript)


def test_check_research_drive_hang_times_out_and_does_not_block(fake_app, mocker):
    """Regression test: os.path.ismount()/os.listdir() have no native
    timeout and can block for minutes on a stale mount (empirically
    measured: 267s on a real stale CIFS mount) or indefinitely on a worse
    network hang. check_research_drive() must give up after a bounded
    deadline -- and, just as important, must not itself block waiting for
    the abandoned worker thread to finish (that would defeat the point of
    the timeout) -- rather than freezing the whole manager's pipeline.
    Patches DRIVE_CHECK_TIMEOUT_SECONDS down to keep this test fast while
    still exercising the real timeout/abandon mechanism; the probe sleeps
    far longer than that patched deadline.
    """
    import time

    fake_app.mode = 'prod'
    fake_app.drive_mount = '/some/mount'
    mocker.patch('system_tasks._check_system.DRIVE_CHECK_TIMEOUT_SECONDS', 0.1)
    mocker.patch.object(
        CheckSystem, '_probe_research_drive', staticmethod(lambda drive_mount: time.sleep(5) or True)
    )

    start = time.monotonic()
    result = CheckSystem(fake_app).check_research_drive()
    elapsed = time.monotonic() - start

    assert result == 1
    assert elapsed < 2  # nowhere near the probe's 5s sleep -- the call didn't wait for it
    assert any('did not respond within' in msg for _, msg in fake_app.transcript)


def test_check_research_drive_prod_mode_unset_drive_mount_returns_1(fake_app):
    fake_app.mode = 'prod'

    result = CheckSystem(fake_app).check_research_drive()

    assert result == 1
    assert any('drive_mount is not set' in msg for _, msg in fake_app.transcript)


# ------------------------------------------------------------
# check_reminders_file
# ------------------------------------------------------------

def test_check_reminders_file_missing_returns_1(fake_app, tmp_path):
    fake_app.reminders_path = str(tmp_path / 'does_not_exist.csv')

    result = CheckSystem(fake_app).check_reminders_file()

    assert result == 1
    assert any('Failed to read reminders.csv' in msg for _, msg in fake_app.transcript)


def test_check_reminders_file_unset_path_returns_1(fake_app):
    result = CheckSystem(fake_app).check_reminders_file()

    assert result == 1
    assert any('reminders_path is not set' in msg for _, msg in fake_app.transcript)


def test_check_reminders_file_missing_columns_returns_1(fake_app, tmp_path):
    reminders_file = tmp_path / 'reminders.csv'
    reminders_file.write_text('subid,unique_id\n')  # missing on_study/remind_ema/remind_feedback
    fake_app.reminders_path = str(reminders_file)

    result = CheckSystem(fake_app).check_reminders_file()

    assert result == 1
    assert any('missing expected columns' in msg for _, msg in fake_app.transcript)


def test_check_reminders_file_valid_returns_0(fake_app, tmp_path):
    reminders_file = tmp_path / 'reminders.csv'
    reminders_file.write_text('subid,unique_id,on_study,remind_ema,remind_feedback\n')
    fake_app.reminders_path = str(reminders_file)

    result = CheckSystem(fake_app).check_reminders_file()

    assert result == 0
    assert not any(level == 'ERROR' for level, _ in fake_app.transcript)


def test_run_includes_reminders_file_check(fake_app, monkeypatch, tmp_path):
    """Regression test: run()'s total used to not reflect reminders.csv's
    state at all -- a broken file only ever surfaced later, at reminder
    send time.
    """
    fake_app.mode = 'test'
    fake_app.participant_manager = MagicMock()
    fake_app.participant_manager.get_participants.return_value = []
    fake_app.reminders_path = str(tmp_path / 'does_not_exist.csv')
    monkeypatch.setattr('system_tasks._check_system.shutil.which', lambda name: '/usr/bin/Rscript')

    result = CheckSystem(fake_app).run()

    assert result == 1
    assert any('Failed to read reminders.csv' in msg for _, msg in fake_app.transcript)
