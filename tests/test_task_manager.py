from datetime import datetime, time

import pytest


def make_manager(fake_app):
    """TaskManager with __init__ bypassed so no background thread starts —
    the logic methods under test here don't need a live thread. _now
    defaults to the real clock and _last_reset_date to today, matching a
    freshly-started real instance's steady state; tests that need to pin
    "now" to a specific moment (e.g. midnight-boundary behavior) override
    tm._now directly -- and, if the fake date differs from the real
    "today" this helper seeded _last_reset_date with, must also set
    tm._last_reset_date = tm._now().date() themselves, or check_tasks()
    sees a spurious date change and resets every run_today flag."""
    from task_managers._task_manager import TaskManager

    tm = TaskManager.__new__(TaskManager)
    tm.app = fake_app
    tm.name = 'TestManager'
    tm.tasks = []
    import queue
    import threading
    tm._tasks_lock = threading.RLock()
    tm._now = datetime.now
    tm._last_reset_date = datetime.now().date()
    tm.task_queue = queue.Queue()
    tm._processing_count = 0
    tm._pause_check_failure_notified = False
    tm._work_state_lock = threading.Lock()
    return tm


def test_add_task_parses_string_time(fake_app):
    tm = make_manager(fake_app)
    tm._now = lambda: datetime(2026, 1, 1, 0, 0, 0)  # before task_time, so run_today stays False
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


def test_add_task_dedupes_identical_system_task(fake_app):
    """Regression test for a real bug (external adversarial review,
    confirmed by inspection): neither the add_system_task/add_r_script_task
    routes nor load_task_schedule() (CSV rows) checked for an existing task
    sharing task_type+task_time before appending -- a duplicate CSV row or
    a repeated API call silently scheduled the same system task twice,
    running it twice daily.
    """
    tm = make_manager(fake_app)
    first = tm.add_task('CHECK_SYSTEM', '03:00:00')

    second = tm.add_task('CHECK_SYSTEM', '03:00:00')

    assert tm.tasks == [first]
    assert second['task_type'] == 'CHECK_SYSTEM'  # still returns a dict, just not appended
    assert any('Not adding' in msg and 'CHECK_SYSTEM' in msg for _, msg in fake_app.transcript)


def test_add_task_does_not_dedupe_different_r_script_paths_at_same_time(fake_app):
    """r_script_path is part of a system task's identity -- two different
    scripts legitimately scheduled for the same time under RUN_R_SCRIPT
    must not be treated as duplicates of each other."""
    tm = make_manager(fake_app)
    tm.add_task('RUN_R_SCRIPT', '03:00:00', r_script_path='one.R')

    tm.add_task('RUN_R_SCRIPT', '03:00:00', r_script_path='two.R')

    assert len(tm.tasks) == 2
    assert {t['r_script_path'] for t in tm.tasks} == {'one.R', 'two.R'}


def test_add_task_does_not_dedupe_participant_tasks_by_type_and_time(fake_app):
    """Dedupe only applies to system tasks (participant_id is None) --
    two different participants both scheduled for 'ema' at the same time
    is completely normal (most participants share the same daily survey
    time) and must not be deduped against each other. Participant-task
    duplication is a different bug/fix (I2, this session's
    load_participants duplicate-unique_id guard), not this one."""
    tm = make_manager(fake_app)
    tm.add_task('ema', '09:00:00', participant_id='000000000')

    tm.add_task('ema', '09:00:00', participant_id='000000001')

    assert len(tm.tasks) == 2


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


def test_check_tasks_fires_task_whose_1s_window_was_missed_while_blocked(fake_app):
    """Regression test for a fixed bug: firing used to require abs(diff) <=
    1 second between "now" and task_time, so a task whose window elapsed
    while the loop was blocked (e.g. an SMS send holding it up to 30s) was
    silently skipped for the entire day, with no log. Firing now only
    requires "now has passed task_time and it hasn't run today" -- no
    narrow window to miss."""
    tm = make_manager(fake_app)
    task_time = time(9, 0, 0)
    tm._now = lambda: datetime.combine(datetime(2026, 1, 1), task_time).replace(
        hour=9, minute=0, second=45
    )  # 45s past the old 1s window
    tm.tasks = [{'task_type': 'ema', 'task_time': task_time, 'run_today': False}]

    tm.check_tasks()

    assert tm.tasks[0]['run_today'] is True
    assert tm.task_queue.get_nowait()['task_type'] == 'ema'


def test_check_tasks_resets_run_today_even_when_tick_skips_exact_midnight_second(fake_app):
    """Regression test for a fixed bug: the run_today reset used to only
    trigger on a tick that landed exactly at 00:00:00 -- a tick that lands
    late (e.g. 00:00:07, after a blocking call) never reset anything,
    silently skipping that whole day's tasks. Reset is now keyed off
    "the calendar date has advanced since the last reset", any tick."""
    tm = make_manager(fake_app)
    tm._last_reset_date = datetime(2025, 12, 31).date()
    tm._now = lambda: datetime(2026, 1, 1, 0, 0, 7)  # 7s past midnight, not exact
    tm.tasks = [{'task_type': 'CHECK_SYSTEM', 'task_time': time(23, 59, 0), 'run_today': True}]

    tm.check_tasks()

    assert tm.tasks[0]['run_today'] is False
    assert tm._last_reset_date == datetime(2026, 1, 1).date()


def test_check_tasks_uses_injected_clock_not_wall_clock(fake_app):
    """Locks in the clock-injection interface itself: check_tasks() must
    consult self._now(), not call datetime.now() directly, so tests can
    control "now" without depending on real wall-clock time."""
    tm = make_manager(fake_app)
    tm._now = lambda: datetime(2026, 1, 1, 23, 59, 0)
    tm.tasks = [{'task_type': 'CHECK_SYSTEM', 'task_time': time(23, 59, 0), 'run_today': False}]

    tm.check_tasks()

    assert tm.tasks[0]['run_today'] is True
    assert tm.task_queue.get_nowait()['task_type'] == 'CHECK_SYSTEM'


def test_add_task_marks_run_today_true_for_time_already_past_today(fake_app):
    """Regression test for a fixed bug: a task loaded (from a persisted
    schedule) or added at runtime for a time already past today used to
    always start run_today=False, so the very next check_tasks() tick fired
    it immediately -- a midday restart replayed the entire morning's tasks.
    """
    tm = make_manager(fake_app)
    tm._now = lambda: datetime(2026, 1, 1, 17, 0, 0)
    tm._last_reset_date = tm._now().date()  # matches the fake "today", no spurious reset

    tm.add_task('CHECK_SYSTEM', '09:00:00')

    assert tm.tasks[0]['run_today'] is True
    tm.check_tasks()
    assert tm.task_queue.empty()


def test_add_task_marks_run_today_false_for_time_still_ahead_today(fake_app):
    tm = make_manager(fake_app)
    tm._now = lambda: datetime(2026, 1, 1, 5, 0, 0)

    tm.add_task('CHECK_SYSTEM', '09:00:00')

    assert tm.tasks[0]['run_today'] is False


def test_add_task_track_false_run_today_ignores_clock(fake_app):
    """An untracked (track=False) task is never scanned by check_tasks() at
    all, so its run_today value is irrelevant in practice -- this just locks
    in the `track and ...` short-circuit so a future change can't
    accidentally make it True and have that matter if the task is ever
    tracked down the line."""
    tm = make_manager(fake_app)
    tm._now = lambda: datetime(2026, 1, 1, 17, 0, 0)

    task = tm.add_task('ema', '09:00:00', participant_id='000000000', one_time=True, track=False)

    assert task['run_today'] is False


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


def test_save_to_csv_escapes_embedded_quote_in_field(tmp_path, fake_app):
    """Locks in a correctness improvement from switching to csv.writer: the
    old f-string writer (f'"{value}"') never escaped an embedded quote,
    corrupting the row. csv.writer doubles it per RFC4180, and the matching
    reader (csv.reader) round-trips it correctly.
    """
    import csv as csv_module

    tm = make_manager(fake_app)
    out_file = tmp_path / 'out.csv'
    data = [{'task_type': 'Smith, "Bob"', 'task_time': time(3, 0, 0)}]

    tm.save_to_csv(data, str(out_file))

    with open(out_file, newline='') as f:
        rows = list(csv_module.reader(f))
    assert rows[1][0] == 'Smith, "Bob"'


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
    fake_app.mode = 'live'
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


def test_run_reports_current_iterations_task_type_not_a_stale_value(fake_app):
    """Regression test for a fixed bug: run()'s except handler used to
    check 'task' in locals() to decide what to report -- but a plain local
    variable stays bound for the rest of the function's life once set on
    any earlier iteration, so a later iteration's exception could
    incorrectly report a PREVIOUS iteration's task_type instead of the
    current one. task is now reassigned to None at the top of every
    iteration, and the dequeue block only ever hands finish_task()'s
    exception handler the task that was actually just pulled (get_nowait()
    replaced the old get(timeout=1); an exception there is only ever
    queue.Empty, handled separately, so this test now exercises the
    equivalent guarantee via two real, distinct queued tasks instead of a
    patched task_queue.get()).
    """
    tm = make_manager(fake_app)
    tm.running = True
    calls = {'n': 0}

    def flaky_process_task(task):
        calls['n'] += 1
        if calls['n'] == 1:
            return 0  # first task (TASK_A) succeeds, no exception
        tm.running = False
        raise RuntimeError('boom on second task')

    tm.process_task = flaky_process_task
    tm.task_queue.put({'task_type': 'TASK_A', 'one_time': False})
    tm.task_queue.put({'task_type': 'TASK_B', 'one_time': False})

    tm.run()

    error_messages = [msg for level, msg in fake_app.transcript if level == 'ERROR']
    assert any('processing task TASK_B:' in msg for msg in error_messages)
    assert not any('processing task TASK_A:' in msg for msg in error_messages)


def test_run_uses_get_nowait_not_blocking_get(fake_app):
    """Locks in the dequeue mechanism itself: run() must call
    task_queue.get_nowait() directly (not the previous blocking
    task_queue.get(timeout=1)) -- get_nowait() is safe here since
    check_tasks() (called immediately before, every iteration, in this same
    thread) is the only other place that ever puts to task_queue. Spies on
    get_nowait() itself (rather than patching .get, which get_nowait() calls
    internally with block=False and would therefore also intercept) to
    confirm it's really the method run() invokes.
    """
    tm = make_manager(fake_app)
    tm.running = True
    task = {'task_type': 'CHECK_SYSTEM', 'task_time': time(3, 0, 0), 'run_today': True}
    tm.tasks = [task]
    tm.task_queue.put(task)
    tm.check_tasks = lambda: None

    real_get_nowait = tm.task_queue.get_nowait
    calls = {'n': 0}

    def spying_get_nowait(*args, **kwargs):
        calls['n'] += 1
        return real_get_nowait(*args, **kwargs)

    tm.task_queue.get_nowait = spying_get_nowait

    def stop_after_one(t):
        tm.running = False
        return 0
    tm.process_task = stop_after_one

    tm.run()

    assert calls['n'] == 1
    assert tm._processing_count == 0


def test_run_outer_catch_all_notifies_coordinators(fake_app, mocker):
    """run()'s outer `except Exception` is a safety net around
    process_task() itself raising (e.g. threading/queue-level issues
    escaping the task's own error handling) -- shared by both
    SystemTaskManager and ParticipantManager's background threads, so this
    represents a genuine system-level malfunction and should alert
    coordinators.
    """
    fake_app.mode = 'live'
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


# ------------------------------------------------------------
# _tasks_lock: real multi-threaded concurrency (not single-threaded
# interleaving simulation) -- these are the tests that actually validate
# the lock does what it exists for. Kept fast (small iteration counts) so
# they don't slow the suite down, but genuinely spin real OS threads.
# ------------------------------------------------------------

def test_concurrent_add_task_no_lost_appends(fake_app):
    """Regression test for the underlying class of bug _tasks_lock exists
    to close: self.tasks is mutated from the background run() thread and
    every Flask request thread. Without a lock, concurrent list.append()
    calls interleaved with check_tasks()'s iteration/mutation could lose
    an append. Hammers add_task() from many threads simultaneously and
    confirms every single one survives.
    """
    import threading

    tm = make_manager(fake_app)
    num_threads = 10
    tasks_per_thread = 20
    stop_checking = threading.Event()

    def add_many(thread_id):
        # Each append is for a distinct participant_id -- add_task()'s
        # system-task dedupe (this session) only applies when
        # participant_id is None, and giving every append the same
        # identity here would collapse them all into one, defeating this
        # test's actual purpose (proving the lock doesn't lose an append),
        # not exercising the dedupe logic at all.
        for i in range(tasks_per_thread):
            tm.add_task('ema', '03:00:00', participant_id=f'{thread_id}_{i}')

    def check_repeatedly():
        # Concurrently hammers the same lock via check_tasks()'s own
        # iteration, same as the real background thread would.
        while not stop_checking.is_set():
            tm.check_tasks()

    checker = threading.Thread(target=check_repeatedly)
    checker.start()
    adders = [threading.Thread(target=add_many, args=(i,)) for i in range(num_threads)]
    for t in adders:
        t.start()
    for t in adders:
        t.join()
    stop_checking.set()
    checker.join()

    assert len(tm.tasks) == num_threads * tasks_per_thread


# ------------------------------------------------------------
# stop() -- bounded join, not an unconditional wait
# ------------------------------------------------------------
#
# Regression tests for a real bug found by an external adversarial review:
# stop() used to be a bare `self.thread.join()` with no timeout. run()'s
# loop only notices self.running=False on its next iteration, which can be
# blocked for a long time inside finish_task() (a real subprocess.run()
# call for a RUN_R_SCRIPT task, bounded at 3h). handle_shutdown() calls
# this synchronously from the SIGTERM/SIGINT signal handler -- an unbounded
# join meant a SIGTERM during a long task could block the entire shutdown
# sequence for up to that same 3h.

def test_stop_returns_promptly_when_thread_is_blocked_on_a_long_task(fake_app, monkeypatch):
    import threading
    import time as time_module
    from task_managers import _task_manager as task_manager_module

    monkeypatch.setattr(task_manager_module, 'STOP_JOIN_TIMEOUT_SECONDS', 0.2)

    tm = make_manager(fake_app)
    tm.running = True
    still_blocked = threading.Event()
    release = threading.Event()

    def blocking_finish_task(task):
        still_blocked.set()
        release.wait(timeout=5)  # simulates a long-running task
        return 0

    tm.finish_task = blocking_finish_task
    tm.thread = threading.Thread(target=tm.run)
    tm.thread.start()
    tm.task_queue.put({'task_type': 'RUN_R_SCRIPT'})
    assert still_blocked.wait(timeout=5)  # thread is now genuinely stuck in finish_task

    start = time_module.monotonic()
    tm.stop()
    elapsed = time_module.monotonic() - start

    assert elapsed < 2  # bounded by the (monkeypatched, short) timeout, not the blocked task
    assert tm.thread.is_alive()  # stop() didn't (and can't) kill the thread, just stopped waiting
    assert any('did not stop within' in msg for _, msg in fake_app.transcript)

    release.set()  # let the blocked thread finish so it doesn't leak past this test
    tm.thread.join(timeout=5)


def test_stop_joins_cleanly_when_thread_is_idle(fake_app):
    import threading

    tm = make_manager(fake_app)
    tm.running = True
    tm.thread = threading.Thread(target=tm.run)
    tm.thread.start()

    tm.stop()

    assert not tm.thread.is_alive()
    assert not any('did not stop within' in msg for _, msg in fake_app.transcript)


def test_concurrent_finish_task_removal_does_not_drop_concurrent_add(fake_app):
    """The exact race _tasks_lock exists to close: finish_task()'s
    `self.tasks[:] = [t for t in self.tasks if t is not task]` snapshots
    self.tasks (via the list comprehension) and then overwrites it --
    without a lock, a concurrent add_task() landing between that read and
    write is silently dropped, with no error anywhere. Repeats many times
    (real thread interleaving is non-deterministic) so this would reliably
    fail if the lock weren't actually preventing the race.
    """
    import threading

    tm = make_manager(fake_app)
    tm.process_task = lambda task: 0
    iterations = 200
    lost_updates = 0

    for _ in range(iterations):
        one_time_task = tm.add_task('ema', '09:00:00', one_time=True)
        added = {}

        def finish():
            tm.finish_task(one_time_task)

        def add_concurrently():
            added['task'] = tm.add_task('CHECK_SYSTEM', '03:00:00')

        t1 = threading.Thread(target=finish)
        t2 = threading.Thread(target=add_concurrently)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        if added['task'] not in tm.tasks:
            lost_updates += 1
        tm.tasks.clear()  # reset for the next iteration

    assert lost_updates == 0


# ------------------------------------------------------------
# has_pending_work() / _pause_processing() -- SystemTaskManager/
# ParticipantManager coordination (base-class side). See
# tests/test_participant_manager.py for ParticipantManager's
# _pause_processing() override, and tests/test_system_task_manager.py for
# confirmation that SystemTaskManager's own _pause_processing() is
# unaffected (always False).
# ------------------------------------------------------------

def test_has_pending_work_false_when_idle(fake_app):
    tm = make_manager(fake_app)

    assert tm.has_pending_work() is False


def test_has_pending_work_true_when_queue_non_empty(fake_app):
    tm = make_manager(fake_app)
    tm.task_queue.put({'task_type': 'CHECK_SYSTEM'})

    assert tm.has_pending_work() is True


def test_has_pending_work_true_when_processing_flag_set(fake_app):
    """Reflects a task actively being processed (queue already empty,
    finish_task() mid-call) -- not just a task sitting in task_queue."""
    tm = make_manager(fake_app)
    tm._processing_count += 1

    assert tm.has_pending_work() is True


def test_has_pending_work_false_after_processing_flag_cleared(fake_app):
    tm = make_manager(fake_app)
    tm._processing_count += 1
    tm._processing_count -= 1

    assert tm.has_pending_work() is False


def test_has_pending_work_true_while_two_busy_spans_overlap(fake_app):
    """Regression test for the bug found by adversarial review: a plain
    threading.Event can only represent 0 or 1 "busy" spans, so whichever of
    two concurrently-open spans (run()'s own scheduled dispatch and
    process_task_with_tracking()'s manual-trigger entry point) finished
    first would clear it and wipe out the still-open other span --
    has_pending_work() would then incorrectly report False while a manual
    task (e.g. a long R script) was still genuinely in flight. Simulates two
    independent entries incrementing _processing_count, then one of them
    exiting -- has_pending_work() must still report True because the other
    span is still open, regardless of which one closed first."""
    tm = make_manager(fake_app)

    # Two independent "busy" sources open concurrently (e.g. run()'s own
    # dispatch of an unrelated scheduled task, plus a manually-triggered
    # process_task_with_tracking() call for a different, still-running task).
    tm._processing_count += 1  # span A opens
    tm._processing_count += 1  # span B opens
    assert tm.has_pending_work() is True

    tm._processing_count -= 1  # span A closes first (e.g. the short scheduled task finishes)
    assert tm._processing_count == 1
    assert tm.has_pending_work() is True  # span B (the still-running manual task) must not be clobbered

    tm._processing_count -= 1  # span B closes
    assert tm._processing_count == 0
    assert tm.has_pending_work() is False


def test_base_pause_processing_always_false(fake_app):
    """Base-class (and SystemTaskManager, which doesn't override it)
    behavior: never pauses, regardless of task_queue/_processing state --
    system tasks always get to run immediately."""
    tm = make_manager(fake_app)
    tm.task_queue.put({'task_type': 'CHECK_SYSTEM'})
    tm._processing_count += 1

    assert tm._pause_processing() is False


def test_run_sets_processing_flag_for_the_duration_of_finish_task(fake_app):
    """Regression-shaped test for the exact span has_pending_work() must
    report "busy": _processing must be set before finish_task() (and
    therefore process_task()) runs, and cleared again once it returns --
    covering the whole processing duration, not just time spent sitting in
    task_queue."""
    tm = make_manager(fake_app)
    tm.running = True
    observed = {}

    def observe_and_stop(task):
        observed['was_set_during_processing'] = tm._processing_count > 0
        tm.running = False
        return 0

    tm.process_task = observe_and_stop
    tm.task_queue.put({'task_type': 'CHECK_SYSTEM'})

    tm.run()

    assert observed['was_set_during_processing'] is True
    assert tm._processing_count == 0  # decremented again after finish_task() returns


def test_run_clears_processing_flag_even_when_finish_task_raises(fake_app):
    """The `finally` around finish_task() in run() must decrement
    _processing_count even on failure -- otherwise a single failed task
    would leave has_pending_work() permanently reporting "busy" forever
    after."""
    tm = make_manager(fake_app)
    tm.running = True

    def failing_process_task(task):
        tm.running = False
        raise RuntimeError('boom')

    tm.process_task = failing_process_task
    tm.task_queue.put({'task_type': 'CHECK_SYSTEM'})

    tm.run()  # must not raise (existing outer except handles this)

    assert tm._processing_count == 0


def test_run_pauses_when_pause_processing_returns_true(fake_app, mocker):
    """When _pause_processing() reports True, run() must skip pulling/
    processing the next task entirely for that iteration -- a due task
    stays in task_queue untouched."""
    tm = make_manager(fake_app)
    tm.running = True
    tm._pause_processing = lambda: True
    tm.process_task = lambda task: 0
    tm.task_queue.put({'task_type': 'CHECK_SYSTEM'})

    def fake_sleep(seconds):
        tm.running = False  # stop after the first paused iteration

    sleep_mock = mocker.patch('task_managers._task_manager.time.sleep', side_effect=fake_sleep)

    tm.run()

    sleep_mock.assert_called_once_with(1)
    assert tm.task_queue.qsize() == 1  # task was never pulled off the queue


def test_run_still_calls_check_tasks_while_paused(fake_app, mocker):
    """check_tasks() (scheduling/due-marking) must still run every
    iteration even while paused -- only the get()/finish_task() step is
    skipped, so a task can still become due and get queued while paused,
    ready to be picked up the moment pausing stops."""
    tm = make_manager(fake_app)
    tm.running = True
    tm._pause_processing = lambda: True
    calls = {'n': 0}

    def counting_check_tasks():
        calls['n'] += 1
        if calls['n'] >= 2:
            tm.running = False

    tm.check_tasks = counting_check_tasks
    mocker.patch('task_managers._task_manager.time.sleep')

    tm.run()

    assert calls['n'] == 2


def test_run_resumes_processing_once_pause_clears(fake_app, mocker):
    """Once _pause_processing() stops reporting True, run() must resume
    pulling/processing the previously-skipped due task on a later
    iteration."""
    tm = make_manager(fake_app)
    tm.running = True
    paused = {'value': True}
    tm._pause_processing = lambda: paused['value']
    task = tm.add_task('CHECK_SYSTEM', '03:00:00')
    tm.task_queue.put(task)
    processed = []

    def process_and_stop(t):
        processed.append(t)
        tm.running = False
        return 0

    tm.process_task = process_and_stop

    def fake_sleep(seconds):
        paused['value'] = False  # unpause after the first paused iteration

    mocker.patch('task_managers._task_manager.time.sleep', side_effect=fake_sleep)

    tm.run()

    assert processed == [task]


# ------------------------------------------------------------
# process_task_with_tracking() -- entry point for callers outside run()'s
# scheduling loop (e.g. _routes.py's manual execute_task/
# execute_r_script_task routes) that need has_pending_work() to reflect a
# manually-triggered task for its whole processing span, the same way
# run()'s own scheduled dispatch already does.
# ------------------------------------------------------------

def test_process_task_with_tracking_sets_processing_flag_for_the_duration(fake_app):
    tm = make_manager(fake_app)
    observed = {}

    def observe(task):
        observed['was_set_during_processing'] = tm._processing_count > 0
        return 0

    tm.process_task = observe

    result = tm.process_task_with_tracking({'task_type': 'RUN_R_SCRIPT'})

    assert result == 0
    assert observed['was_set_during_processing'] is True
    assert tm._processing_count == 0  # decremented again after process_task() returns


def test_process_task_with_tracking_clears_processing_flag_even_when_process_task_raises(fake_app):
    tm = make_manager(fake_app)

    def failing_process_task(task):
        raise RuntimeError('boom')

    tm.process_task = failing_process_task

    with pytest.raises(RuntimeError):
        tm.process_task_with_tracking({'task_type': 'RUN_R_SCRIPT'})

    assert tm._processing_count == 0


def test_process_task_with_tracking_and_run_can_be_concurrently_busy(fake_app):
    """Regression test for the exact bug fixed this session: run()'s own
    scheduled dispatch and process_task_with_tracking()'s manual-trigger
    entry point are independent "busy" sources on the same manager
    instance, and can be concurrently open -- e.g. a Flask thread runs a
    manually-triggered long R script via process_task_with_tracking() while
    run()'s own background thread separately dequeues and finishes an
    unrelated short scheduled task. With the old threading.Event-based
    _processing flag, whichever span finished first would clear the shared
    Event and wipe out the still-open other span -- has_pending_work()
    would then incorrectly report False while the manual task was still
    genuinely in flight. Runs process_task_with_tracking() on a background
    thread with a slow/blocking process_task, and while it's still open,
    drives run() through one full scheduled-task cycle on this thread;
    has_pending_work() must still report True the whole time, including
    right after run()'s own span closes.
    """
    import threading

    tm = make_manager(fake_app)
    tm.running = True

    manual_task_started = threading.Event()
    release_manual_task = threading.Event()
    manual_result = {}

    def slow_manual_process_task(task):
        manual_task_started.set()
        release_manual_task.wait(timeout=5)
        return 0

    manual_thread = threading.Thread(
        target=lambda: manual_result.update(
            code=tm.process_task_with_tracking({'task_type': 'RUN_R_SCRIPT'})
        )
    )

    # Swap in the slow process_task only for the manual span; run()'s own
    # dispatch (below) uses a separate, fast process_task via finish_task().
    tm.process_task = slow_manual_process_task
    manual_thread.start()
    assert manual_task_started.wait(timeout=5)
    assert tm._processing_count == 1
    assert tm.has_pending_work() is True

    # Now drive run()'s own scheduled dispatch through one full cycle for an
    # unrelated short task, concurrently with the still-open manual span.
    observed_during_run = {}

    def fast_scheduled_process_task(task):
        observed_during_run['pending_with_both_spans_open'] = tm.has_pending_work()
        observed_during_run['count_with_both_spans_open'] = tm._processing_count
        tm.running = False
        return 0

    tm.process_task = fast_scheduled_process_task
    tm.task_queue.put({'task_type': 'CHECK_SYSTEM'})
    tm.run()

    # run()'s own span has now closed (finished before the manual span) --
    # the manual span must NOT have been clobbered by that.
    assert observed_during_run['pending_with_both_spans_open'] is True
    assert observed_during_run['count_with_both_spans_open'] == 2
    assert tm._processing_count == 1
    assert tm.has_pending_work() is True

    release_manual_task.set()
    manual_thread.join(timeout=5)
    assert manual_result['code'] == 0
    assert tm._processing_count == 0
    assert tm.has_pending_work() is False


def test_has_pending_work_true_while_process_task_with_tracking_runs(fake_app):
    """The whole point of process_task_with_tracking(): a manually-triggered
    system task (e.g. a manually-triggered R script, up to 3h) must make
    has_pending_work() report True for its entire span, not just for a
    scheduled task dispatched through run()."""
    tm = make_manager(fake_app)
    observed = {}

    def observe(task):
        observed['pending'] = tm.has_pending_work()
        return 0

    tm.process_task = observe

    tm.process_task_with_tracking({'task_type': 'RUN_R_SCRIPT'})

    assert observed['pending'] is True
    assert tm.has_pending_work() is False


# ------------------------------------------------------------
# run()'s _pause_processing() call is now guarded -- an exception there
# must not silently kill this unsupervised background thread, mirroring
# the existing check_tasks()-raises-doesn't-crash protection.
# ------------------------------------------------------------

def test_run_pause_processing_exception_does_not_crash_loop(fake_app):
    tm = make_manager(fake_app)
    tm.running = True
    calls = {'n': 0}

    def flaky_pause_processing():
        calls['n'] += 1
        if calls['n'] == 1:
            raise RuntimeError('pause check boom')
        tm.running = False
        return False

    tm._pause_processing = flaky_pause_processing

    tm.run()  # must not raise

    assert calls['n'] == 2
    assert any('pause check boom' in msg for _, msg in fake_app.transcript)


def test_run_does_not_pause_on_the_iteration_pause_processing_raised(fake_app):
    """A raising _pause_processing() must be treated as should_pause=False
    for that iteration (fail open, not fail paused) -- a due task in
    task_queue still gets processed on that very same iteration rather than
    being stuck behind a broken pause check forever."""
    tm = make_manager(fake_app)
    tm.running = True
    tm.check_tasks = lambda: None  # isolates this test to the pause/dequeue steps
    task = {'task_type': 'CHECK_SYSTEM', 'task_time': time(3, 0, 0), 'run_today': True}
    tm.tasks = [task]
    tm.task_queue.put(task)
    processed = []

    def flaky_pause_processing():
        raise RuntimeError('pause check boom')

    tm._pause_processing = flaky_pause_processing

    def process_and_stop(t):
        processed.append(t)
        tm.running = False
        return 0

    tm.process_task = process_and_stop

    tm.run()

    assert processed == [task]


# ------------------------------------------------------------
# run()'s pause-check failure escalates to notify_coordinators -- a
# persistently failing _pause_processing() (e.g. self.app.system_task_manager
# becomes permanently unset) used to only log a transcript line forever,
# indistinguishable from routine log noise. Escalation is edge-triggered
# (fires once per failure episode), not level-triggered (once per iteration)
# or one-shot-for-the-process-lifetime -- see _pause_check_failure_notified.
# ------------------------------------------------------------

def test_pause_check_failure_notifies_coordinators_once(fake_app, mocker):
    tm = make_manager(fake_app)
    tm.running = True
    notify = mocker.patch('task_managers._task_manager.notify_coordinators', return_value=0)

    def flaky_pause_processing():
        tm.running = False
        raise RuntimeError('pause check boom')

    tm._pause_processing = flaky_pause_processing

    tm.run()

    notify.assert_called_once()
    message = notify.call_args[0][1]
    assert message.startswith('[3001] ')
    assert 'pause check boom' in message
    assert tm._pause_check_failure_notified is True


def test_pause_check_persistent_failure_does_not_spam_notify_coordinators(fake_app, mocker):
    """A pause-check that keeps failing on every subsequent iteration must
    only alert coordinators once for the whole unbroken failure run -- the
    transcript ERROR line can (and does) repeat every iteration, but
    notify_coordinators must not."""
    tm = make_manager(fake_app)
    tm.running = True
    notify = mocker.patch('task_managers._task_manager.notify_coordinators', return_value=0)
    calls = {'n': 0}

    def always_flaky_pause_processing():
        calls['n'] += 1
        if calls['n'] >= 5:
            tm.running = False
        raise RuntimeError('pause check boom')

    tm._pause_processing = always_flaky_pause_processing
    mocker.patch('task_managers._task_manager.time.sleep')

    tm.run()

    assert calls['n'] == 5
    notify.assert_called_once()
    assert sum(1 for _, msg in fake_app.transcript if 'pause check boom' in msg) == 5


def test_pause_check_failure_re_notifies_after_recovering_and_failing_again(fake_app, mocker):
    """Edge-triggered, not "only ever once for the process lifetime": once
    _pause_processing() recovers (a later call succeeds), the failure latch
    resets, so a subsequent failure fires a second notify_coordinators
    call."""
    tm = make_manager(fake_app)
    tm.running = True
    notify = mocker.patch('task_managers._task_manager.notify_coordinators', return_value=0)
    mocker.patch('task_managers._task_manager.time.sleep')
    tm.check_tasks = lambda: None  # isolates this test to the pause-check step; task_queue stays empty

    calls = {'n': 0}

    def scripted_pause_processing():
        calls['n'] += 1
        if calls['n'] in (1, 3):
            raise RuntimeError('pause check boom')
        if calls['n'] == 4:
            tm.running = False
        return False  # iteration 2 (and 4, if reached): a successful recovery

    tm._pause_processing = scripted_pause_processing

    tm.run()

    assert calls['n'] == 4
    assert notify.call_count == 2


# ------------------------------------------------------------
# Midnight-rollover duplicate-SMS fix: run()'s dequeue block reaffirms
# run_today=True for the task it's actually processing right now, since
# check_tasks()'s date-rollover branch can flip run_today back to False on
# a task still sitting un-drained in task_queue during a pause spanning
# midnight (see ParticipantManager._pause_processing()).
# ------------------------------------------------------------

def test_run_reaffirms_run_today_after_midnight_rollover_while_queued(fake_app):
    """A task queued before midnight (run_today=True), still un-drained in
    task_queue when check_tasks()'s rollover branch resets its run_today
    back to False (simulated directly here -- the same object a paused
    background thread would have flipped), must end up with
    run_today=True again once run() actually dequeues and processes it --
    otherwise it would incorrectly fire a second time later the same day.
    """
    tm = make_manager(fake_app)
    tm.running = True
    task = {'task_type': 'ema', 'task_time': time(23, 0, 0), 'run_today': True}
    tm.tasks = [task]
    tm.task_queue.put(task)
    # Simulates check_tasks()'s own date-rollover branch flipping this same
    # still-queued task dict's run_today back to False.
    task['run_today'] = False
    # Isolates this test to run()'s own dequeue step -- not check_tasks(),
    # which is exercised separately above.
    tm.check_tasks = lambda: None

    def stop_after_one(t):
        tm.running = False
        return 0

    tm.process_task = stop_after_one

    tm.run()

    assert task['run_today'] is True


class _ExplodingRunTodayTask(dict):
    """A task dict whose `run_today` reaffirmation write raises, simulating
    a failure in the `with self._tasks_lock: task['run_today'] = True` block
    inside run()'s dequeue-to-processing span. Only `run_today` explodes --
    every other read/write (task_type, task_time, .get(), etc.) behaves like
    a normal dict, including the dict(...) construction below, which uses
    the C-level bulk-merge path and does not go through this __setitem__
    override at all.
    """
    def __setitem__(self, key, value):
        if key == 'run_today':
            raise RuntimeError('run_today reaffirm boom')
        super().__setitem__(key, value)


def test_run_today_reaffirmation_failure_still_decrements_processing_count(fake_app, mocker):
    """Fix 2 regression test: the run_today reaffirmation now happens
    inside the same try/finally that decrements _processing_count, not in
    its own block before the try. If reaffirming run_today (or acquiring
    _tasks_lock) ever raises, _processing_count -- already incremented by
    the dequeue block -- must still be decremented back down (not left
    permanently stuck), and the failure must be reported through the
    normal task-processing exception handler: the same transcript ERROR
    message shape as any other task-processing failure, plus a
    notify_coordinators alert, rather than crashing run()'s thread.
    """
    fake_app.mode = 'live'
    tm = make_manager(fake_app)
    tm.running = True
    notify = mocker.patch('task_managers._task_manager.notify_coordinators', return_value=0)
    tm.check_tasks = lambda: None
    task = _ExplodingRunTodayTask({'task_type': 'CHECK_SYSTEM', 'task_time': time(3, 0, 0), 'run_today': True})
    tm.tasks = [task]
    tm.task_queue.put(task)

    def stop_after_one(t):
        tm.running = False
        return 0

    tm.process_task = stop_after_one  # never actually reached -- the raise happens before finish_task()

    # The raise happens before finish_task()/process_task() ever runs, so
    # stop_after_one above never gets a chance to flip tm.running = False --
    # unlike every other run()-exception test in this file, whose
    # process_task IS reached and does the stopping. task_queue is already
    # empty after this one failed dequeue, so the loop's very next iteration
    # takes the "task is None" branch and calls time.sleep(1); stop the loop
    # there instead.
    def fake_sleep(seconds):
        tm.running = False

    mocker.patch('task_managers._task_manager.time.sleep', side_effect=fake_sleep)

    tm.run()  # must not raise -- the outer except in run() must catch this

    assert tm._processing_count == 0  # not left permanently stuck
    assert any(
        'An error occurred while processing task CHECK_SYSTEM' in msg and 'run_today reaffirm boom' in msg
        for _, msg in fake_app.transcript
    )
    notify.assert_called_once()
    message = notify.call_args[0][1]
    assert message.startswith('[3001] ')
    assert 'CHECK_SYSTEM' in message
    assert 'run_today reaffirm boom' in message


def test_run_leaves_run_today_true_for_same_day_no_rollover(fake_app):
    """Confirms no regression to the ordinary (no midnight rollover) case:
    a task processed same-day, with no rollover in between, still ends up
    with run_today=True -- this should already hold trivially, since
    check_tasks() itself sets it True at queue time, but this locks it in
    against the new reaffirm-at-dequeue-time logic ever accidentally
    clearing it instead.
    """
    tm = make_manager(fake_app)
    tm.running = True
    task = {'task_type': 'CHECK_SYSTEM', 'task_time': time(3, 0, 0), 'run_today': True}
    tm.tasks = [task]
    tm.task_queue.put(task)
    tm.check_tasks = lambda: None

    def stop_after_one(t):
        tm.running = False
        return 0

    tm.process_task = stop_after_one

    tm.run()

    assert task['run_today'] is True
