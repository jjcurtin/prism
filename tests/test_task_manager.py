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


def test_run_reports_new_iterations_task_type_not_a_stale_locals_value(fake_app, mocker):
    """Regression test for a fixed bug: run()'s except handler used to
    check 'task' in locals() to decide what to report -- but a plain local
    variable stays bound for the rest of the function's life once set on
    any earlier iteration, so a later iteration's exception raised BEFORE
    task_queue.get() returns incorrectly reported the PREVIOUS iteration's
    task_type instead of '?'. task is now reassigned to None at the top of
    every iteration.
    """
    tm = make_manager(fake_app)
    tm.running = True
    tm.process_task = lambda task: 0
    calls = {'n': 0}
    real_get = tm.task_queue.get

    def flaky_get(*args, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            return {'task_type': 'REAL_TASK'}
        tm.running = False
        raise RuntimeError('boom before get() returns')

    tm.task_queue.get = flaky_get

    tm.run()

    error_messages = [msg for level, msg in fake_app.transcript if level == 'ERROR']
    assert any('processing task ?:' in msg for msg in error_messages)
    assert not any('processing task REAL_TASK:' in msg for msg in error_messages)


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
