import os

from system_tasks._check_system import CheckSystem


DRIVE_SOURCED_ATTRS = [
    'system_task_schedule_path', 'study_coordinators_path',
    'participants_path'
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
                 '_system_task.py']:
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
    system_task_schedule.csv/study_coordinators.csv/study_participants.csv
    under a local ../config/ directory that hasn't held these files since
    config went drive-sourced-only (config/README.md, 2026-07-09) -- the
    diagnostics menu would always report failure regardless of actual
    system health. Now checks the already-resolved self.app.*_path
    attributes instead.
    """
    src_dir = make_fake_src_tree(tmp_path)
    monkeypatch.chdir(src_dir)
    paths = make_drive_sourced_files(tmp_path)
    del paths['study_coordinators_path']  # simulate an unset attribute
    for attr, path in paths.items():
        setattr(fake_app, attr, path)

    result = CheckSystem(fake_app).check_file_system()

    assert result == 1
    assert any('study_coordinators_path' in msg for _, msg in fake_app.transcript)
