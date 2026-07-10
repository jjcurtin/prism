import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

from system_tasks._check_system import CheckSystem


DRIVE_SOURCED_ATTRS = [
    'system_task_schedule_path', 'study_coordinators_path',
    'script_pipeline_path', 'participants_path'
]


def make_fake_src_tree(tmp_path):
    """Mimics the sibling layout check_file_system expects when run from
    src/ (../data, ../scripts, ../logs, and a system_tasks/ subfolder with
    the real task filenames) and returns the fake src/ dir to chdir into."""
    src_dir = tmp_path / 'src'
    src_dir.mkdir()
    (tmp_path / 'data').mkdir()
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'logs').mkdir()
    system_tasks_dir = src_dir / 'system_tasks'
    system_tasks_dir.mkdir()
    for name in ['_check_system.py', '_pulldown_qualtrics_data.py', '_pulldown_followmee_data.py',
                 '_run_r_script_pipeline.py', '_system_task.py']:
        (system_tasks_dir / name).write_text('')
    return src_dir


def make_drive_sourced_files(tmp_path):
    paths = {}
    for attr in DRIVE_SOURCED_ATTRS:
        f = tmp_path / f'{attr}.csv'
        f.write_text('x')
        paths[attr] = str(f)
    return paths


def test_check_file_system_all_present_returns_0(tmp_path, fake_app, monkeypatch):
    src_dir = make_fake_src_tree(tmp_path)
    monkeypatch.chdir(src_dir)
    for attr, path in make_drive_sourced_files(tmp_path).items():
        setattr(fake_app, attr, path)

    result = CheckSystem(fake_app).check_file_system()

    assert result == 0


def test_check_file_system_missing_local_dir_returns_1(tmp_path, fake_app, monkeypatch):
    src_dir = make_fake_src_tree(tmp_path)
    (tmp_path / 'logs').rmdir()
    monkeypatch.chdir(src_dir)
    for attr, path in make_drive_sourced_files(tmp_path).items():
        setattr(fake_app, attr, path)

    result = CheckSystem(fake_app).check_file_system()

    assert result == 1
    assert any("'../logs' directory is missing" in msg for _, msg in fake_app.transcript)


def test_check_file_system_missing_drive_sourced_file_returns_1(tmp_path, fake_app, monkeypatch):
    src_dir = make_fake_src_tree(tmp_path)
    monkeypatch.chdir(src_dir)
    paths = make_drive_sourced_files(tmp_path)
    os.remove(paths['study_coordinators_path'])
    for attr, path in paths.items():
        setattr(fake_app, attr, path)

    result = CheckSystem(fake_app).check_file_system()

    assert result == 1
    assert any('study_coordinators_path' in msg for _, msg in fake_app.transcript)


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


def test_check_file_system_missing_drive_sourced_attr_returns_1(tmp_path, fake_app, monkeypatch):
    """Regression test for a fixed bug: check_file_system used to look for
    system_task_schedule.csv/study_coordinators.csv/script_pipeline.csv/
    study_participants.csv under a local ../config/ directory that hasn't
    held these files since config went drive-sourced-only
    (config/README.md, 2026-07-09) -- the diagnostics menu would always
    report failure regardless of actual system health. Now checks the
    already-resolved self.app.*_path attributes instead.
    """
    src_dir = make_fake_src_tree(tmp_path)
    monkeypatch.chdir(src_dir)
    paths = make_drive_sourced_files(tmp_path)
    del paths['script_pipeline_path']  # simulate an unset attribute
    for attr, path in paths.items():
        setattr(fake_app, attr, path)

    result = CheckSystem(fake_app).check_file_system()

    assert result == 1
    assert any('script_pipeline_path' in msg for _, msg in fake_app.transcript)


def test_check_tests_subprocess_succeeds_returns_0(tmp_path, fake_app):
    fake_app.repo_root = tmp_path
    mock_result = MagicMock(returncode=0, stdout='152 passed\n', stderr='')

    with patch('system_tasks._check_system.subprocess.run', return_value=mock_result) as mock_run:
        result = CheckSystem(fake_app).check_tests()

    assert result == 0
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == [sys.executable, '-m', 'pytest', 'tests', 'tests_interface', '-q']
    assert kwargs['cwd'] == str(tmp_path)
    assert kwargs['capture_output'] is True
    assert kwargs['text'] is True
    assert kwargs['timeout'] == 120
    assert not any(msg_type == 'ERROR' for msg_type, _ in fake_app.transcript)


def test_check_tests_subprocess_reports_failures_returns_1(tmp_path, fake_app):
    fake_app.repo_root = tmp_path
    failure_output = "\n".join(f"line {i}" for i in range(30)) + "\nFAILED tests/test_foo.py::test_bar\n1 failed, 151 passed\n"
    mock_result = MagicMock(returncode=1, stdout=failure_output, stderr='')

    with patch('system_tasks._check_system.subprocess.run', return_value=mock_result):
        result = CheckSystem(fake_app).check_tests()

    assert result == 1
    error_messages = [msg for msg_type, msg in fake_app.transcript if msg_type == 'ERROR']
    assert len(error_messages) == 1
    assert 'reported failures' in error_messages[0]
    assert 'FAILED tests/test_foo.py::test_bar' in error_messages[0]
    # only the last ~20 lines should be logged, not the full firehose
    assert 'line 0\n' not in error_messages[0]


def test_check_tests_subprocess_times_out_returns_1(tmp_path, fake_app):
    fake_app.repo_root = tmp_path

    with patch(
        'system_tasks._check_system.subprocess.run',
        side_effect=subprocess.TimeoutExpired(cmd=['pytest'], timeout=120, output='stuck...\n', stderr=''),
    ):
        result = CheckSystem(fake_app).check_tests()

    assert result == 1
    error_messages = [msg for msg_type, msg in fake_app.transcript if msg_type == 'ERROR']
    assert len(error_messages) == 1
    assert 'timed out' in error_messages[0]
