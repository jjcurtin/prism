from datetime import datetime, time

import pytest


def make_manager(fake_app):
    """TaskManager with __init__ bypassed so no background thread starts —
    the logic methods under test here don't need a live thread."""
    from task_managers._task_manager import TaskManager

    tm = TaskManager.__new__(TaskManager)
    tm.app = fake_app
    tm.name = 'TestManager'
    tm.tasks = []
    import queue
    tm.task_queue = queue.Queue()
    return tm


def test_add_task_parses_string_time(fake_app):
    tm = make_manager(fake_app)
    tm.add_task('CHECK_SYSTEM', '03:00:00')
    assert tm.tasks[0]['task_type'] == 'CHECK_SYSTEM'
    assert tm.tasks[0]['task_time'] == time(3, 0, 0)
    assert tm.tasks[0]['run_today'] is False


def test_add_task_accepts_time_object_directly(fake_app):
    tm = make_manager(fake_app)
    tm.add_task('CHECK_SYSTEM', time(4, 30, 0))
    assert tm.tasks[0]['task_time'] == time(4, 30, 0)


def test_add_task_r_script_path_empty_string_becomes_none(fake_app):
    tm = make_manager(fake_app)
    tm.add_task('RUN_R_SCRIPT', '03:00:00', r_script_path='')
    assert tm.tasks[0]['r_script_path'] is None


def test_add_task_r_script_path_literal_none_string_becomes_none(fake_app):
    tm = make_manager(fake_app)
    tm.add_task('RUN_R_SCRIPT', '03:00:00', r_script_path='None')
    assert tm.tasks[0]['r_script_path'] is None


def test_add_task_r_script_path_real_value_kept(fake_app):
    tm = make_manager(fake_app)
    tm.add_task('RUN_R_SCRIPT', '03:00:00', r_script_path='cleanup.R')
    assert tm.tasks[0]['r_script_path'] == 'cleanup.R'


def test_add_task_participant_id_set_when_given(fake_app):
    tm = make_manager(fake_app)
    tm.add_task('EMA', '09:00:00', participant_id='000000000')
    assert tm.tasks[0]['participant_id'] == '000000000'


def test_add_task_participant_id_absent_when_not_given(fake_app):
    tm = make_manager(fake_app)
    tm.add_task('CHECK_SYSTEM', '03:00:00')
    assert 'participant_id' not in tm.tasks[0]


def test_check_tasks_queues_a_due_task(fake_app):
    tm = make_manager(fake_app)
    now = datetime.now().time()
    tm.tasks = [{'task_type': 'CHECK_SYSTEM', 'task_time': now, 'run_today': False}]

    tm.check_tasks()

    assert tm.tasks[0]['run_today'] is True
    assert tm.task_queue.get_nowait()['task_type'] == 'CHECK_SYSTEM'


def test_check_tasks_does_not_requeue_a_task_already_run_today(fake_app):
    tm = make_manager(fake_app)
    now = datetime.now().time()
    tm.tasks = [{'task_type': 'CHECK_SYSTEM', 'task_time': now, 'run_today': True}]

    tm.check_tasks()

    assert tm.task_queue.empty()


def test_check_tasks_leaves_a_not_yet_due_task_alone(fake_app):
    tm = make_manager(fake_app)
    far_future = time(23, 59, 59)
    tm.tasks = [{'task_type': 'CHECK_SYSTEM', 'task_time': far_future, 'run_today': False}]

    tm.check_tasks()

    assert tm.task_queue.empty()
    assert tm.tasks[0]['run_today'] is False


def test_save_to_csv_writes_header_and_rows(tmp_path, fake_app):
    tm = make_manager(fake_app)
    out_file = tmp_path / 'out.csv'
    data = [{'task_type': 'CHECK_SYSTEM', 'task_time': time(3, 0, 0)}]

    tm.save_to_csv(data, str(out_file))

    lines = out_file.read_text().splitlines()
    assert lines[0] == '"task_type","task_time"'
    assert lines[1] == '"CHECK_SYSTEM","03:00:00"'


def test_save_to_csv_empty_data_writes_no_header(tmp_path, fake_app):
    tm = make_manager(fake_app)
    out_file = tmp_path / 'out.csv'

    tm.save_to_csv([], str(out_file))

    assert out_file.read_text() == '\n'


def test_save_to_csv_failure_logs_error_instead_of_raising(fake_app):
    tm = make_manager(fake_app)

    tm.save_to_csv([{'a': 1}], '/nonexistent_dir/out.csv')

    assert fake_app.transcript[0][0] == 'ERROR'
    assert 'Failed to save data to CSV' in fake_app.transcript[0][1]


def test_process_task_not_implemented_by_base_class(fake_app):
    tm = make_manager(fake_app)
    with pytest.raises(NotImplementedError):
        tm.process_task({})
