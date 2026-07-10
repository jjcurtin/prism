from unittest.mock import MagicMock

from system_tasks._check_system import CheckSystem


def test_run_only_checks_research_drive_and_participants_not_filesystem(fake_app):
    """Regression test for a fixed bug: CHECK_SYSTEM used to also run
    check_file_system, a static local directory/file existence check
    (../data, ../scripts, ../logs, hardcoded cwd-relative) that's a
    deployment-verification concern, not a runtime diagnostic -- it failed
    in practice with "The '../scripts' directory is missing" on a
    perfectly healthy system just because cwd wasn't exactly src/. run()
    now only checks things that reflect live system state: the research
    drive connection and loaded-participant data integrity. Deliberately
    doesn't touch the filesystem at all here (no fake src/ tree, no
    chdir) to prove run() no longer depends on it.
    """
    fake_app.mode = 'test'
    fake_app.participant_manager = MagicMock()
    fake_app.participant_manager.get_participants.return_value = []

    result = CheckSystem(fake_app).run()

    assert result == 0
    assert not any('directory is missing' in msg for _, msg in fake_app.transcript)
    assert not any('file' in msg.lower() and 'missing' in msg.lower() for _, msg in fake_app.transcript)


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


def test_check_research_drive_prod_mode_unset_drive_mount_returns_1(fake_app):
    fake_app.mode = 'prod'

    result = CheckSystem(fake_app).check_research_drive()

    assert result == 1
    assert any('drive_mount is not set' in msg for _, msg in fake_app.transcript)
