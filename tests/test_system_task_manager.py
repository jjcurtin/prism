import os
import queue
from datetime import time


def make_manager(fake_app):
    """SystemTaskManager with __init__ bypassed (no background thread, no
    filesystem-dependent get_task_types()/load_task_schedule() at
    construction time) — tests call the individual methods explicitly."""
    from task_managers._system_task_manager import SystemTaskManager

    stm = SystemTaskManager.__new__(SystemTaskManager)
    stm.app = fake_app
    stm.name = 'SystemTaskManager'
    stm.tasks = []
    stm.task_queue = queue.Queue()
    stm.task_types = {}
    return stm


def test_get_task_types_lists_task_files_excluding_base_class():
    from task_managers._system_task_manager import SystemTaskManager

    stm = SystemTaskManager.__new__(SystemTaskManager)
    src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src')
    cwd = os.getcwd()
    try:
        os.chdir(src_dir)
        task_types = stm.get_task_types()
    finally:
        os.chdir(cwd)

    assert 'CHECK_SYSTEM' in task_types
    assert task_types['CHECK_SYSTEM'] == 'CheckSystem'
    assert '_SYSTEM_TASK' not in task_types  # base class file excluded
    assert 'SYSTEM_TASK' not in task_types


def test_get_r_script_tasks_lists_only_R_files(tmp_path, fake_app):
    (tmp_path / 'cleanup.R').write_text('# cleanup')
    (tmp_path / 'analysis.R').write_text('# analysis')
    (tmp_path / 'notes.txt').write_text('not an R script')
    fake_app.r_scripts_dir = str(tmp_path)
    stm = make_manager(fake_app)

    result = stm.get_r_script_tasks()

    assert result == {'cleanup': 'cleanup', 'analysis': 'analysis'}


def test_load_task_schedule_parses_valid_rows(tmp_path, fake_app):
    schedule_file = tmp_path / 'system_task_schedule.csv'
    schedule_file.write_text(
        '"task_type","task_time","r_script_path","run_today"\n'
        '"CHECK_SYSTEM","03:00:00","","no"\n'
    )
    fake_app.system_task_schedule_path = str(schedule_file)
    stm = make_manager(fake_app)
    stm.task_types = {'CHECK_SYSTEM': 'CheckSystem'}
    stm.file_path = str(schedule_file)

    stm.load_task_schedule()

    assert len(stm.tasks) == 1
    assert stm.tasks[0]['task_type'] == 'CHECK_SYSTEM'
    assert stm.tasks[0]['task_time'] == time(3, 0, 0)


def test_load_task_schedule_skips_blank_lines(tmp_path, fake_app):
    schedule_file = tmp_path / 'system_task_schedule.csv'
    schedule_file.write_text(
        '"task_type","task_time","r_script_path","run_today"\n'
        '"CHECK_SYSTEM","03:00:00","","no"\n'
        '\n'
        '"CHECK_SYSTEM","04:00:00","","no"\n'
    )
    fake_app.system_task_schedule_path = str(schedule_file)
    stm = make_manager(fake_app)
    stm.task_types = {'CHECK_SYSTEM': 'CheckSystem'}
    stm.file_path = str(schedule_file)

    stm.load_task_schedule()

    assert len(stm.tasks) == 2


def test_load_task_schedule_unknown_task_type_skips_row_and_logs(tmp_path, fake_app):
    schedule_file = tmp_path / 'system_task_schedule.csv'
    schedule_file.write_text(
        '"task_type","task_time","r_script_path","run_today"\n'
        '"NOT_A_REAL_TASK","03:00:00","","no"\n'
    )
    fake_app.system_task_schedule_path = str(schedule_file)
    stm = make_manager(fake_app)
    stm.task_types = {'CHECK_SYSTEM': 'CheckSystem'}
    stm.file_path = str(schedule_file)

    stm.load_task_schedule()

    assert stm.tasks == []
    assert any('Unknown task type: NOT_A_REAL_TASK' in msg for _, msg in fake_app.transcript)


def test_load_task_schedule_sorts_by_task_time(tmp_path, fake_app):
    schedule_file = tmp_path / 'system_task_schedule.csv'
    schedule_file.write_text(
        '"task_type","task_time","r_script_path","run_today"\n'
        '"CHECK_SYSTEM","09:00:00","","no"\n'
        '"CHECK_SYSTEM","03:00:00","","no"\n'
    )
    fake_app.system_task_schedule_path = str(schedule_file)
    stm = make_manager(fake_app)
    stm.task_types = {'CHECK_SYSTEM': 'CheckSystem'}
    stm.file_path = str(schedule_file)

    stm.load_task_schedule()

    assert [t['task_time'] for t in stm.tasks] == [time(3, 0, 0), time(9, 0, 0)]


def test_load_task_schedule_missing_file_logs_error_not_crash(fake_app):
    stm = make_manager(fake_app)
    stm.file_path = '/nonexistent/system_task_schedule.csv'

    stm.load_task_schedule()

    assert stm.tasks == []
    assert any('Task schedule file not found' in msg for _, msg in fake_app.transcript)


def test_get_task_schedule_formats_task_time_as_string(fake_app):
    stm = make_manager(fake_app)
    stm.tasks = [{'task_type': 'CHECK_SYSTEM', 'task_time': time(3, 0, 0), 'run_today': False}]

    result = stm.get_task_schedule()

    assert result == [{
        'task_type': 'CHECK_SYSTEM',
        'task_time': '03:00:00',
        'r_script_path': '',
        'run_today': False,
    }]


def test_save_tasks_sorts_before_writing(tmp_path, fake_app):
    schedule_file = tmp_path / 'system_task_schedule.csv'
    fake_app.system_task_schedule_path = str(schedule_file)
    stm = make_manager(fake_app)
    stm.file_path = str(schedule_file)
    stm.tasks = [
        {'task_type': 'B', 'task_time': time(9, 0, 0)},
        {'task_type': 'A', 'task_time': time(3, 0, 0)},
    ]

    stm.save_tasks()

    lines = schedule_file.read_text().splitlines()
    assert lines[1] == '"A","03:00:00"'
    assert lines[2] == '"B","09:00:00"'


def test_remove_task_removes_matching_task_and_saves(tmp_path, fake_app):
    schedule_file = tmp_path / 'system_task_schedule.csv'
    fake_app.system_task_schedule_path = str(schedule_file)
    stm = make_manager(fake_app)
    stm.file_path = str(schedule_file)
    stm.tasks = [{'task_type': 'CHECK_SYSTEM', 'task_time': time(3, 0, 0)}]

    result = stm.remove_task('CHECK_SYSTEM', task_time='03:00:00')

    assert result == 0
    assert stm.tasks == []


def test_remove_task_not_found_returns_1(fake_app):
    stm = make_manager(fake_app)
    stm.tasks = []

    result = stm.remove_task('CHECK_SYSTEM', task_time='03:00:00')

    assert result == 1
    assert any('not found' in msg for _, msg in fake_app.transcript)
