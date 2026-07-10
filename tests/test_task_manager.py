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


def test_add_task_one_time_defaults_to_false(fake_app):
    """Existing callers that don't pass `one_time` must keep getting a
    permanent, recurring task -- this is the default the whole rest of the
    engine (check_tasks/run) relies on for every pre-existing task type."""
    tm = make_manager(fake_app)
    tm.add_task('CHECK_SYSTEM', '03:00:00')
    assert tm.tasks[0]['one_time'] is False


def test_add_task_one_time_true_when_requested(fake_app):
    tm = make_manager(fake_app)
    tm.add_task('ema', '09:00:00', participant_id='000000000', one_time=True)
    assert tm.tasks[0]['one_time'] is True


def test_add_task_returns_the_created_task_dict(fake_app):
    tm = make_manager(fake_app)
    task = tm.add_task('ema', '09:00:00', participant_id='000000000', one_time=True)
    assert task is tm.tasks[0]


def test_add_task_track_defaults_to_true(fake_app):
    """Every existing recurring/scheduled caller relies on this -- a task
    must land in self.tasks for the background poller to ever see it."""
    tm = make_manager(fake_app)
    task = tm.add_task('CHECK_SYSTEM', '03:00:00')
    assert tm.tasks == [task]


def test_add_task_track_false_not_added_to_tasks(fake_app):
    """Regression test for a real duplicate-SMS bug: _routes.py's
    send_survey adds a one-time task with task_time=now, which used to
    always append to self.tasks -- immediately eligible for the background
    poller's own check_tasks() tick (its ~1s window starts the moment the
    task is appended), racing the synchronous finish_task() call and
    sending a genuine duplicate SMS (two distinct Twilio SIDs observed for
    one EMA send). track=False must keep the task out of self.tasks
    entirely while still returning the task dict for the caller to pass to
    finish_task() itself."""
    tm = make_manager(fake_app)
    task = tm.add_task('ema', '09:00:00', participant_id='000000000', one_time=True, track=False)
    assert tm.tasks == []
    assert task['task_type'] == 'ema'


def test_add_task_track_false_task_time_now_never_reaches_check_tasks_queue(fake_app):
    """End-to-end version of the regression above: even with task_time set
    to the exact current moment (send_survey's real usage) and check_tasks()
    actually run immediately afterward, an untracked task can never be
    independently queued -- it was never in self.tasks for check_tasks() to
    scan in the first place."""
    tm = make_manager(fake_app)
    now_str = datetime.now().strftime('%H:%M:%S')
    tm.add_task('ema', now_str, participant_id='000000000', one_time=True, track=False)

    tm.check_tasks()

    assert tm.task_queue.empty()


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


# ------------------------------------------------------------
# finish_task / one_time cleanup
# ------------------------------------------------------------

def test_finish_task_removes_one_time_task_after_success(fake_app):
    tm = make_manager(fake_app)
    tm.process_task = lambda task: 0
    task = tm.add_task('ema', '09:00:00', participant_id='000000000', one_time=True)

    result = tm.finish_task(task)

    assert result == 0
    assert tm.tasks == []


def test_finish_task_removes_one_time_task_after_failure_no_retry(fake_app):
    """A failed one-time task must still be removed immediately -- decision
    is "no retry", not "retry until it succeeds"."""
    tm = make_manager(fake_app)
    tm.process_task = lambda task: -1
    task = tm.add_task('ema', '09:00:00', participant_id='000000000', one_time=True)

    result = tm.finish_task(task)

    assert result == -1
    assert tm.tasks == []


def test_finish_task_leaves_recurring_task_in_place(fake_app):
    """The default (one_time=False) behavior -- used by every pre-existing
    recurring task type (ema/ema_reminder/feedback/feedback_reminder/system
    tasks) -- must be completely unaffected: the task stays scheduled after
    processing, exactly like before finish_task existed."""
    tm = make_manager(fake_app)
    tm.process_task = lambda task: 0
    task = tm.add_task('ema_reminder', '10:00:00', participant_id='000000000')

    tm.finish_task(task)

    assert tm.tasks == [task]


def test_finish_task_only_removes_the_matching_task_by_identity(fake_app):
    """A one-time 'ema' send for a participant must not remove that same
    participant's unrelated permanent recurring 'ema' task, even though
    both share task_type + participant_id -- removal is by object identity,
    not by field matching."""
    tm = make_manager(fake_app)
    tm.process_task = lambda task: 0
    recurring = tm.add_task('ema', '09:00:00', participant_id='000000000')
    one_time = tm.add_task('ema', '09:00:05', participant_id='000000000', one_time=True)

    tm.finish_task(one_time)

    assert tm.tasks == [recurring]


def test_run_calls_finish_task_and_removes_one_time_task(fake_app):
    """The polling run() loop must route every task through finish_task
    (not process_task directly) so one-time cleanup applies there too, not
    just to direct/manual invocations."""
    tm = make_manager(fake_app)
    tm.running = True
    tm.process_task = lambda task: 0
    task = tm.add_task('ema', '09:00:00', participant_id='000000000', one_time=True)

    def stop_after_one(t):
        tm.running = False
        return 0
    tm.process_task = stop_after_one
    tm.task_queue.put(task)

    tm.run()

    assert tm.tasks == []


def test_run_leaves_non_one_time_task_scheduled(fake_app):
    tm = make_manager(fake_app)
    tm.running = True
    task = tm.add_task('CHECK_SYSTEM', '03:00:00')

    def stop_after_one(t):
        tm.running = False
        return 0
    tm.process_task = stop_after_one
    tm.task_queue.put(task)

    tm.run()

    assert tm.tasks == [task]


def test_run_check_tasks_exception_does_not_crash_loop(fake_app):
    """Regression test: check_tasks() used to run outside run()'s try/
    except entirely -- any exception there (a future code change, or an
    unexpected task-dict shape) would silently kill the whole background
    thread with no transcript trace at all, unlike a task-processing
    failure, which was already caught. Confirms the loop survives a
    check_tasks() failure and keeps calling it on the next tick.
    """
    tm = make_manager(fake_app)
    tm.running = True
    calls = {'n': 0}

    def flaky_check_tasks():
        calls['n'] += 1
        if calls['n'] == 1:
            raise RuntimeError('boom')
        tm.running = False  # stop the loop on the second, successful call

    tm.check_tasks = flaky_check_tasks

    tm.run()  # must not raise

    assert calls['n'] == 2
    assert any('boom' in msg for _, msg in fake_app.transcript)


def test_run_notify_coordinators_failure_does_not_crash_loop(fake_app, mocker):
    """Regression test: the coordinator-alert call inside run()'s own
    exception handler used to be unguarded -- if it too failed (e.g. the
    same broken-Twilio-credentials root cause that likely caused the
    original failure being reported), that second exception propagated
    out of the handler entirely and silently killed the background
    thread the first time anything went wrong.
    """
    fake_app.mode = 'prod'
    tm = make_manager(fake_app)
    tm.running = True
    mocker.patch(
        'task_managers._task_manager.notify_coordinators',
        side_effect=RuntimeError('twilio also broken'),
    )

    def failing_process_task(task):
        tm.running = False
        raise RuntimeError('original failure')

    tm.process_task = failing_process_task
    tm.task_queue.put({'task_type': 'CHECK_SYSTEM'})

    tm.run()  # must not raise

    assert any('original failure' in msg for _, msg in fake_app.transcript)
    assert any(
        'Also failed to notify coordinators' in msg and 'twilio also broken' in msg
        for _, msg in fake_app.transcript
    )


def test_run_outer_catch_all_notifies_coordinators(fake_app, mocker):
    """run()'s outer `except Exception` is a safety net around
    process_task() itself raising (e.g. threading/queue-level issues
    escaping the task's own error handling) -- shared by both
    SystemTaskManager and ParticipantManager's background threads, so this
    represents a genuine system-level malfunction and should alert
    coordinators.
    """
    fake_app.mode = 'prod'
    tm = make_manager(fake_app)
    tm.running = True
    notify = mocker.patch('task_managers._task_manager.notify_coordinators', return_value=0)

    def failing_process_task(task):
        tm.running = False  # stop run()'s loop right after this task is handled
        raise RuntimeError('boom')

    tm.process_task = failing_process_task
    tm.task_queue.put({'task_type': 'CHECK_SYSTEM'})

    tm.run()

    notify.assert_called_once()
    message = notify.call_args[0][1]
    assert message.startswith('[3001] ')
    assert 'CHECK_SYSTEM' in message
    assert 'boom' in message
