import queue
import threading
from datetime import datetime, time


def make_manager(fake_app):
    """SystemTaskManager with __init__ bypassed (no background thread, no
    filesystem-dependent get_task_types()/load_task_schedule() at
    construction time) — tests call the individual methods explicitly."""
    from task_managers._system_task_manager import SystemTaskManager

    stm = SystemTaskManager.__new__(SystemTaskManager)
    stm.app = fake_app
    stm.name = 'SystemTaskManager'
    stm.tasks = []
    stm._tasks_lock = threading.RLock()
    stm._now = datetime.now
    stm._last_reset_date = datetime.now().date()
    stm.task_queue = queue.Queue()
    stm._processing = threading.Event()
    stm.task_types = {}
    return stm


def test_get_task_types_derived_from_static_registry():
    from task_managers._system_task_manager import SystemTaskManager, TASK_CLASSES

    stm = SystemTaskManager.__new__(SystemTaskManager)

    task_types = stm.get_task_types()

    assert set(task_types) == set(TASK_CLASSES)
    assert task_types['CHECK_SYSTEM'] == 'CheckSystem'
    assert task_types['RUN_R_SCRIPT'] == 'RunRScript'


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


def test_load_task_schedule_tolerates_extra_columns(tmp_path, fake_app):
    """Regression test for the exact crash reported in practice: a
    system_task_schedule.csv with a 5th `one_time` column (written by the
    old save_to_csv default-header inference -- see save_tasks() docstring)
    used to blow up load_task_schedule() with `UnboundLocalError: cannot
    access local variable 'task_type'`, raised from inside the except
    ValueError handler itself after the fixed-width positional unpack
    failed on 5 fields instead of 4. csv.DictReader maps by column name, so
    an unexpected extra column is simply ignored rather than corrupting the
    whole row.
    """
    schedule_file = tmp_path / 'system_task_schedule.csv'
    schedule_file.write_text(
        '"task_type","task_time","r_script_path","run_today","one_time"\n'
        '"CHECK_SYSTEM","17:59:30","None","True","False"\n'
        '"RUN_R_SCRIPT","18:02:30","Test.R","False","False"\n'
    )
    fake_app.system_task_schedule_path = str(schedule_file)
    stm = make_manager(fake_app)
    stm.task_types = {'CHECK_SYSTEM': 'CheckSystem', 'RUN_R_SCRIPT': 'RunRScript'}
    stm.file_path = str(schedule_file)

    stm.load_task_schedule()

    assert len(stm.tasks) == 2
    assert not any('cannot access local variable' in msg for _, msg in fake_app.transcript)


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
    assert lines[0] == '"task_type","task_time","r_script_path","run_today"'
    assert lines[1] == '"A","03:00:00","",""'
    assert lines[2] == '"B","09:00:00","",""'


def test_save_tasks_writes_fixed_schema_regardless_of_task_dict_keys(tmp_path, fake_app):
    """Regression test for a fixed bug: save_tasks() used to derive CSV
    headers from whichever task happened to be data[0] (save_to_csv's old
    default), so a task carrying extra TaskManager-generic keys (e.g.
    one_time, unconditionally set by add_task) would silently make every
    row gain an extra column -- load_task_schedule()'s reader, which
    expected a fixed 4-column schema, then crashed with
    `UnboundLocalError: cannot access local variable 'task_type'` on the
    very next load. save_tasks() now always writes exactly
    SCHEDULE_CSV_HEADERS, independent of what's actually in the dicts.
    """
    schedule_file = tmp_path / 'system_task_schedule.csv'
    fake_app.system_task_schedule_path = str(schedule_file)
    stm = make_manager(fake_app)
    stm.file_path = str(schedule_file)
    stm.tasks = [
        {'task_type': 'CHECK_SYSTEM', 'task_time': time(3, 0, 0), 'run_today': False, 'one_time': False},
        {'task_type': 'RUN_R_SCRIPT', 'task_time': time(4, 0, 0), 'r_script_path': 'Test.R', 'run_today': False, 'one_time': False},
    ]

    stm.save_tasks()

    header, *rows = schedule_file.read_text().splitlines()
    assert header == '"task_type","task_time","r_script_path","run_today"'
    assert all(line.count(',') == 3 for line in rows)  # exactly 4 columns, every row

    stm.task_types = {'CHECK_SYSTEM': 'CheckSystem', 'RUN_R_SCRIPT': 'RunRScript'}
    stm.load_task_schedule()
    assert len(stm.tasks) == 2


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


# --- process_task dispatch --------------------------------------------

def test_process_task_unknown_task_type_logs_and_returns_neg1(fake_app):
    """A task_type absent from TASK_CLASSES (e.g. a stale schedule-CSV row)
    just logs and returns -1 -- not a coordinator-alert-worthy system
    failure, since a task type that was never registered here could never
    have run successfully before either.
    """
    stm = make_manager(fake_app)

    result = stm.process_task({'task_type': 'NOT_A_REAL_TASK'})

    assert result == -1
    assert any('Unknown task type: NOT_A_REAL_TASK' in msg for _, msg in fake_app.transcript)


def test_process_task_dispatches_to_registered_class_without_r_script(fake_app, mocker):
    stm = make_manager(fake_app)
    fake_task_class = mocker.MagicMock()
    fake_task_class.return_value.execute.return_value = 0
    mocker.patch.dict('task_managers._system_task_manager.TASK_CLASSES', {'CHECK_SYSTEM': fake_task_class})

    result = stm.process_task({'task_type': 'CHECK_SYSTEM'})

    assert result == 0
    fake_task_class.assert_called_once_with(fake_app)


def test_process_task_dispatches_with_r_script_path(fake_app, mocker):
    stm = make_manager(fake_app)
    fake_task_class = mocker.MagicMock()
    fake_task_class.return_value.execute.return_value = 1

    mocker.patch.dict('task_managers._system_task_manager.TASK_CLASSES', {'RUN_R_SCRIPT': fake_task_class})

    result = stm.process_task({'task_type': 'RUN_R_SCRIPT', 'r_script_path': 'cleanup.R'})

    assert result == 1
    fake_task_class.assert_called_once_with(fake_app, 'cleanup.R')


# ------------------------------------------------------------
# _pause_processing() -- SystemTaskManager/ParticipantManager coordination
# (see task_managers/CLAUDE.md). SystemTaskManager does not override the
# base class's _pause_processing() hook -- system tasks (including
# RUN_R_SCRIPT, up to 3h) always get priority and must never be paused for
# anything, regardless of its own or any other manager's queue/processing
# state. See tests/test_participant_manager.py for ParticipantManager's
# overridden behavior, which does defer.
# ------------------------------------------------------------

def test_pause_processing_always_false_regardless_of_own_state(fake_app):
    stm = make_manager(fake_app)
    stm.task_queue.put({'task_type': 'RUN_R_SCRIPT'})
    stm._processing.set()

    assert stm._pause_processing() is False


def test_run_never_pauses_even_with_a_due_system_task(fake_app):
    """End-to-end confirmation: SystemTaskManager's own run() loop never
    skips a due task via the pause mechanism -- it processes it
    immediately, exactly as before this coordination feature existed."""
    stm = make_manager(fake_app)
    stm.running = True
    task = stm.add_task('CHECK_SYSTEM', '03:00:00')
    stm.task_queue.put(task)
    processed = []

    def process_and_stop(t):
        processed.append(t)
        stm.running = False
        return 0

    stm.process_task = process_and_stop

    stm.run()

    assert processed == [task]
