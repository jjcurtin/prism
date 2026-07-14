"""base class for task managers"""

from datetime import date, datetime, time as dt_time
from typing import Any, Callable
import csv
import queue
import threading
import time

from _helper import notify_coordinators
from _error_codes import code_prefix
from _types import App

# A task is a small, loosely-structured dict (not every key is present on
# every task -- e.g. `r_script_path`/`participant_id` are only set by the
# callers that need them; see add_task() below). Kept as `dict[str, Any]`
# rather than a TypedDict/dataclass, matching this codebase's existing
# convention of passing plain dicts as tasks throughout task_managers/,
# system_tasks/, and _routes.py.
Task = dict[str, Any]

# Bounds stop()'s thread.join() -- see stop()'s own comment for why this
# can't just wait indefinitely. Comfortably above run()'s own 1s
# task_queue.get(timeout=1) poll interval (the common case: the loop is idle
# or between tasks, and notices self.running=False on its very next poll),
# nowhere close to system_tasks/_run_r_script.py's R_SCRIPT_TIMEOUT_SECONDS
# (3h) -- that gap is the whole point.
STOP_JOIN_TIMEOUT_SECONDS = 10

class TaskManager():
    def __init__(self, app: App, name: str) -> None:
        self.app = app
        self.name = name
        self.running = True
        self.tasks: list[Task] = []
        # self.tasks is mutated/iterated from at least two threads: this
        # manager's own background run() thread (check_tasks()/
        # finish_task()'s removal), and every Flask request-handling thread
        # (add_task()/remove_task()/etc., via _routes.py). Python's GIL
        # prevents literal memory corruption, but it does NOT prevent a
        # read-then-write race -- e.g. finish_task()'s `self.tasks[:] = [t
        # for t in self.tasks if t is not task]` snapshots self.tasks via
        # the list comprehension, then overwrites it; a concurrent
        # add_task() append landing in that window is silently dropped,
        # with no error or log line anywhere. An RLock (not a plain Lock)
        # because finish_task() calls process_task() -- a subclass method
        # that, for ParticipantManager, calls back into methods that also
        # need this same protection (get_participant() et al) -- while
        # already holding it in some call paths.
        #
        # Deliberately NOT held across process_task() itself (see
        # finish_task() below) -- that can include a real network call
        # (SMS send, up to _helper.SMS_SEND_TIMEOUT_SECONDS) or an R script
        # execution, and holding a lock across either would block every
        # other thread trying to touch self.tasks for that entire duration
        # -- trading one hang for another.
        self._tasks_lock = threading.RLock()
        # Set for the exact duration finish_task() is actively processing a
        # task (from just before process_task() is called to just after it
        # returns, including one_time cleanup -- see finish_task() below),
        # cleared the rest of the time. Combined with `not
        # self.task_queue.empty()` in has_pending_work() below, this is how
        # a sibling manager (see _pause_processing()) can tell "this manager
        # has work queued up OR is mid-task" without needing to inspect
        # self.tasks/task_queue internals directly. An Event, not a plain
        # bool -- no test/caller here actually blocks on it, but it's the
        # conventional thread-safe primitive for a flag read/written across
        # threads, and costs nothing over a bool for that guarantee.
        self._processing = threading.Event()
        # Injected rather than calling datetime.now()/date.today() inline in
        # check_tasks()/add_task() below -- an ambient wall-clock read is an
        # input a test can't control, so tests end up either not exercising
        # midnight/boundary behavior at all or doing so flakily (real sleeps
        # racing real wall-clock ticks). Tests bypass __init__ (see
        # make_manager() in tests/test_task_manager.py et al) and set
        # tm._now to a fixed callable directly.
        self._now: Callable[[], datetime] = datetime.now
        # Tracks the last calendar date check_tasks() reset run_today flags
        # for. Seeded to *today*, not None/some sentinel -- add_task() above
        # already pre-computes the correct run_today for each task as it's
        # loaded (see its own comment), so the very first check_tasks() tick
        # after startup must NOT treat "no reset has ever happened" as "the
        # date has advanced" and wipe those freshly-computed flags back to
        # False, which would silently undo that fix and replay the whole
        # morning on every restart, exactly like before. Compared by date
        # equality (not an exact 00:00:00 tick) on every later call -- a
        # tick that lands late (e.g. after a blocking SMS send held the loop
        # up) still resets on whichever tick comes next.
        self._last_reset_date: date = self._now().date()
        self.task_queue: queue.Queue[Task] = queue.Queue()
        self.thread = threading.Thread(target = self.run)
        self.thread.start()

    def add_task(
        self,
        task_type: str,
        task_time: str | dt_time,
        r_script_path: str | None = None,
        participant_id: str | None = None,
        one_time: bool = False,
        track: bool = True,
    ) -> Task:
        """`r_script_path` accepts the literal string "None" as an
        empty/none value in addition to "". Callers that pass this through a
        URL path segment (e.g. _routes.py's add_system_task route) can't
        encode a truly empty string there, so they send the literal "None"
        instead.

        `one_time` marks a task for automatic removal (via `finish_task`)
        immediately after it finishes processing once -- success or
        failure, no retry -- instead of persisting indefinitely like every
        other task this engine manages. Defaults to False so every existing
        caller/task keeps its current permanent, recurring behavior
        unchanged.

        `track` controls whether the task is appended to `self.tasks` at
        all -- the list the background `run()` thread's `check_tasks()`
        scans every ~1s to decide what's due. Defaults to True (every
        existing recurring/scheduled caller). A caller that's about to
        `finish_task()` this exact task synchronously right now (e.g.
        _routes.py's send_survey, whose task_time is `datetime.now()`) must
        pass `track=False`: otherwise there's a real race between that
        synchronous call and the background thread's own `check_tasks()`
        tick, which sees a brand-new task scheduled for "now" -- within its
        1-second firing window from the moment it's appended -- and can
        independently enqueue + process the same task a second time before
        the synchronous call finishes, sending a real duplicate SMS
        (confirmed in practice: two distinct Twilio SIDs for one EMA send).

        Returns the created task dict so a caller that needs to process it
        synchronously (see `finish_task`) can reference this exact task
        instance later, rather than re-looking it up by task_type +
        participant_id -- which could otherwise ambiguously match a
        different, unrelated task sharing the same type/participant (e.g. a
        one-time 'ema' send and a participant's recurring daily 'ema'
        task).
        """
        parsed_task_time = datetime.strptime(task_time, '%H:%M:%S').time() if isinstance(task_time, str) else task_time
        task_dict: Task = {
            'task_type': task_type,
            'task_time': parsed_task_time,
        }
        if r_script_path is not None:
            if r_script_path == "" or r_script_path == "None":
                task_dict['r_script_path'] = None
            else:
                task_dict['r_script_path'] = r_script_path
        # A tracked task whose time-of-day has already passed "now" starts
        # pre-marked run_today=True -- otherwise check_tasks()'s "now >=
        # task_time and not run_today" firing condition (below) would fire
        # it on the very next tick, whether it was just loaded from a
        # persisted schedule at startup (a midday restart replaying the
        # whole morning) or freshly added via a route/menu for a time
        # that's already passed today (which should just wait for
        # tomorrow). An untracked one-time task (track=False) is never
        # scanned by check_tasks() at all, so this doesn't affect it.
        task_dict['run_today'] = track and parsed_task_time <= self._now().time()
        task_dict['one_time'] = one_time
        if participant_id is not None:
            task_dict['participant_id'] = participant_id
        if track:
            with self._tasks_lock:
                # Deduped for a system task (participant_id is None) only --
                # a participant's recurring tasks are already covered by
                # ParticipantManager's own I2 invariant (at most one
                # recurring task per (task_type, participant_id) pair),
                # enforced upstream of this call (load_participants'/
                # add_participant's duplicate-unique_id rejection, this
                # session). Found by an external adversarial review,
                # confirmed by inspection: neither the add_system_task/
                # add_r_script_task routes nor load_task_schedule() (CSV
                # rows) checked for an existing task sharing
                # task_type+task_time(+r_script_path) before appending --
                # a duplicate CSV row or a repeated API call silently
                # scheduled the same system task twice, running it twice
                # daily. r_script_path is part of the identity (not just
                # task_type+task_time) so two different scripts legitimately
                # scheduled for the same time under RUN_R_SCRIPT aren't
                # treated as duplicates of each other.
                is_duplicate_system_task = participant_id is None and any(
                    t.get('task_type') == task_type
                    and t.get('task_time') == parsed_task_time
                    and t.get('r_script_path') == task_dict.get('r_script_path')
                    for t in self.tasks
                )
                if is_duplicate_system_task:
                    self.app.add_to_transcript(
                        f"Not adding {task_type} at {parsed_task_time}: an identical system task "
                        "is already scheduled.", "WARNING"
                    )
                else:
                    self.tasks.append(task_dict)
        return task_dict
    
    def save_to_csv(self, data: list[Task], file_path: str, headers: list[str] | None = None) -> None:
        """`headers` should be passed explicitly by any caller with a
        documented on-disk schema to persist (e.g. SystemTaskManager's
        system_task_schedule.csv, README.md Appendix A) --
        deriving it from
        `data[0].keys()` instead is fragile: every task dict does carry
        `one_time` (unconditionally set in add_task above), but only tasks
        given an explicit r_script_path/participant_id carry those keys, so
        the inferred header set silently depends on which task happens to
        be first and can drift out of sync with whatever reads this file
        back (a real bug: load_task_schedule()'s reader hardcoded a fixed
        4-column schema and broke the moment a saved row picked up
        `one_time` as a 5th column from this inference).
        """
        try:
            if headers is None:
                headers = list(data[0].keys()) if data else []
            with open(file_path, 'w', newline = '') as f:
                writer = csv.writer(f, quoting = csv.QUOTE_ALL, lineterminator = '\n')
                writer.writerow(headers)
                for row in data:
                    writer.writerow([row.get(header, '') for header in headers])
        except Exception as e:
            self.app.add_to_transcript(f"Failed to save data to CSV at {file_path}: {e}", "ERROR")

    def check_tasks(self) -> None:
        """A task fires once its scheduled time has passed for the day and
        it hasn't already run today -- not a narrow "within 1 second of
        now" window, which a blocked tick (e.g. an SMS send holding this
        loop up to SMS_SEND_TIMEOUT_SECONDS) could elapse without this loop
        ever observing, silently skipping that task for the entire day.
        run_today is reset for the whole list whenever the calendar date
        has advanced since the last reset, not only on a tick that happens
        to land exactly at 00:00:00.
        """
        now = self._now()
        today = now.date()
        with self._tasks_lock:
            if today != self._last_reset_date:
                for task in self.tasks:
                    task['run_today'] = False
                self._last_reset_date = today
            for task in self.tasks:
                task_time = task['task_time']
                if now >= datetime.combine(today, task_time) and not task['run_today']:
                    self.task_queue.put(task)
                    task['run_today'] = True

    def process_task(self, task: Task) -> int:
        raise NotImplementedError("Subclasses must implement this method.")

    def has_pending_work(self) -> bool:
        """True if this manager has a task sitting in task_queue waiting to
        be pulled, or is currently inside finish_task() actively processing
        one -- i.e. there's work either queued or in flight right now. Used
        by ParticipantManager's _pause_processing() override (see
        _participant_manager.py) to give SystemTaskManager unconditional
        priority: SystemTaskManager itself never calls this on anyone (its
        own _pause_processing() stays the base-class False, see below).
        """
        return not self.task_queue.empty() or self._processing.is_set()

    def _pause_processing(self) -> bool:
        """Overridable hook, checked once per run() iteration before this
        manager pulls its next task off task_queue. Returns False here
        (never pause) -- the base-class/SystemTaskManager behavior: system
        tasks (including RUN_R_SCRIPT, up to 3h) always get to run
        immediately and are never deferred for anything else.
        ParticipantManager overrides this to pause its own SMS-sending loop
        whenever SystemTaskManager reports pending/in-progress work (see
        _participant_manager.py's override), giving system tasks
        unconditional priority over resuming SMS sends -- deliberately with
        no starvation safeguard, confirmed by explicit user decision.
        """
        return False

    def finish_task(self, task: Task) -> int:
        """Process `task` and, if it's flagged `one_time`, remove it from
        self.tasks immediately afterward -- regardless of whether
        process_task succeeded or failed, and with no retry. This is the
        single place one-time cleanup happens, shared by both the normal
        polling loop below (`run()`) and any direct/manual invocation (e.g.
        a route that needs a synchronous result right now instead of
        waiting for the next `check_tasks` tick) -- so a one-time task's
        lifecycle is identical no matter which path finishes it. The
        removal is a harmless no-op for a task that was never tracked in
        the first place (`add_task(..., track=False)`, see its docstring).

        Removal matches by object identity (`is`), not by task_type/
        participant_id/value equality, so it can never remove a different
        task that merely looks similar (e.g. a participant's permanent
        recurring 'ema' task sitting alongside a one-time 'ema' send for
        that same participant).
        """
        # process_task() runs outside the lock deliberately -- it can
        # perform a real network call (SMS send) or R script execution,
        # and holding _tasks_lock across that would block every other
        # thread trying to touch self.tasks for the entire duration.
        result = self.process_task(task)
        if task.get('one_time'):
            with self._tasks_lock:
                self.tasks[:] = [t for t in self.tasks if t is not task]
        return result

    # note: self._processing is set/cleared around the finish_task() call
    # site in run() below, not inside finish_task() itself -- finish_task()
    # is also invoked directly by _routes.py's two synchronous, RA-triggered
    # routes (send_survey and the manual feedback-send route), which
    # deliberately bypass run() entirely and must stay unaffected by this
    # coordination mechanism (see task_managers/CLAUDE.md).

    def run(self) -> None:
        while self.running:
            # check_tasks() must never be allowed to raise unguarded here --
            # this loop is this manager's *entire* processing pipeline
            # (every scheduled task, forever, until PRISM restarts); nothing
            # else calls it, and nothing supervises/restarts this thread if
            # it dies. Before this try/except, any exception here (a future
            # code change, or an unexpected task-dict shape) would silently
            # kill the thread with no transcript trace at all -- unlike a
            # task-processing failure below, which was already caught.
            try:
                self.check_tasks()
            except Exception as e:
                self.app.add_to_transcript(f"An error occurred while checking scheduled tasks in {self.name}: {e}", "ERROR")
            # Checked after check_tasks() (so scheduling/due-marking is
            # never skipped -- a task can still become due and get queued
            # while paused) but before task_queue.get()/finish_task() below
            # (so a due task isn't actually pulled and processed while
            # paused). Base class/SystemTaskManager: always False, never
            # pauses. ParticipantManager overrides this to defer to
            # SystemTaskManager's pending/in-progress work -- see
            # _pause_processing()'s own docstring above.
            if self._pause_processing():
                time.sleep(1)  # matches this loop's own ~1s poll cadence
                continue
            # Reassigned every iteration (rather than relying on 'task' in
            # locals()) -- a plain local variable stays bound for the rest
            # of this function's life once first assigned on any earlier
            # iteration, so a later exception raised before task_queue.get()
            # returns would otherwise report a PREVIOUS iteration's task
            # instead of "unknown".
            task: Task | None = None
            try:
                task = self.task_queue.get(timeout = 1)
                # self._processing is set for the exact span finish_task()
                # is actively running (cleared in a `finally` so it's never
                # left stuck set by a finish_task()/process_task() failure)
                # -- has_pending_work() above reports "busy" for this whole
                # duration, not just the time a task previously sat in
                # task_queue waiting to be pulled.
                self._processing.set()
                try:
                    result = self.finish_task(task)
                finally:
                    self._processing.clear()
                if result != 0:
                    self.app.add_to_transcript(f"Task {task['task_type']} failed with error code {result}.", "ERROR")
            except queue.Empty:
                pass
            except Exception as e:
                task_type = task.get('task_type', '?') if task is not None else '?'
                self.app.add_to_transcript(f"An error occurred while processing task {task_type}: {e}", "ERROR")
                # Defensively wrapped: notify_coordinators() itself failing
                # (e.g. the same broken-Twilio-credentials root cause that
                # may have caused the failure being reported here) must
                # never propagate out of this handler -- that would crash
                # this loop over a failed *alert about* a failure, which is
                # exactly the cascade that used to silently kill this
                # thread the first time anything went wrong.
                try:
                    notify_coordinators(self.app, code_prefix('3001') + f"PRISM system failure: an error occurred while processing task {task_type} in {self.name}. Error: {e}")
                except Exception as notify_error:
                    self.app.add_to_transcript(f"Also failed to notify coordinators about that error: {notify_error}", "ERROR")
                # note: changed print to add_to_transcript and removed the thing that kills the manager
        self.app.add_to_transcript(f"{self.name} processor stopped.", "INFO")

    def stop(self) -> None:
        """Bounded join, not an unconditional wait -- found by an external
        adversarial review: this used to be a bare `self.thread.join()`
        with no timeout. run()'s loop only notices self.running=False on
        its next iteration, which can be blocked for a long time inside
        finish_task()->process_task() (a real subprocess.run() call for a
        RUN_R_SCRIPT task, bounded at R_SCRIPT_TIMEOUT_SECONDS = 3h in
        system_tasks/_run_r_script.py). handle_shutdown() (run_prism.py)
        calls this synchronously from the SIGTERM/SIGINT signal handler,
        before unlinking the PID file and os._exit()-ing -- an unbounded
        join here meant a SIGTERM during a long R script could block the
        entire shutdown sequence for up to that same 3h, defeating the
        whole point of sending a termination signal.

        A timeout does not kill the thread (Python threads can't be force-
        killed) -- it just stops *this call* from waiting past
        STOP_JOIN_TIMEOUT_SECONDS, so a caller like handle_shutdown can
        still proceed with the rest of its own shutdown sequence (which
        ends in os._exit(), which DOES terminate every thread, non-daemon
        or not) instead of hanging indefinitely on this one.
        """
        self.running = False
        self.thread.join(timeout = STOP_JOIN_TIMEOUT_SECONDS)
        if self.thread.is_alive():
            self.app.add_to_transcript(
                f"{self.name} did not stop within {STOP_JOIN_TIMEOUT_SECONDS}s -- likely still "
                "processing a long-running task; continuing shutdown without waiting further.",
                "WARNING",
            )