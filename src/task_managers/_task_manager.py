"""base class for task managers"""

from datetime import datetime, time as dt_time
from typing import Any
import queue
import threading

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

class TaskManager():
    def __init__(self, app: App, name: str) -> None:
        self.app = app
        self.name = name
        self.running = True
        self.tasks: list[Task] = []
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
        task_dict: Task = {
            'task_type': task_type,
            'task_time': datetime.strptime(task_time, '%H:%M:%S').time() if isinstance(task_time, str) else task_time,
        }
        if r_script_path is not None:
            if r_script_path == "" or r_script_path == "None":
                task_dict['r_script_path'] = None
            else:
                task_dict['r_script_path'] = r_script_path
        task_dict['run_today'] = False
        task_dict['one_time'] = one_time
        if participant_id is not None:
            task_dict['participant_id'] = participant_id
        if track:
            self.tasks.append(task_dict)
        return task_dict
    
    def save_to_csv(self, data: list[Task], file_path: str, headers: list[str] | None = None) -> None:
        """`headers` should be passed explicitly by any caller with a
        documented on-disk schema to persist (e.g. SystemTaskManager's
        system_task_schedule.csv, config/README.md) -- deriving it from
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
            with open(file_path, 'w') as f:
                f.write(','.join(f'"{header}"' for header in headers) + '\n')
                for row in data:
                    f.write(','.join(f'"{str(row.get(header, ""))}"' for header in headers) + '\n')
        except Exception as e:
            self.app.add_to_transcript(f"Failed to save data to CSV at {file_path}: {e}", "ERROR")

    def check_tasks(self) -> None:
        """A task fires once its scheduled time is within 1 second of "now"
        (this runs frequently enough that the window doesn't need to be
        wider), and won't fire again until run_today is reset back to False
        at the next midnight tick.
        """
        current_time = datetime.now().time()
        if current_time.hour == 0 and current_time.minute == 0 and current_time.second == 0:
            for task in self.tasks:
                task['run_today'] = False
        for task in self.tasks:
            task_time = task['task_time']
            diff = abs((datetime.combine(datetime.today(), current_time) - datetime.combine(datetime.today(), task_time)).total_seconds())
            if diff <= 1 and not task['run_today']:
                self.task_queue.put(task)
                task['run_today'] = True

    def process_task(self, task: Task) -> int:
        raise NotImplementedError("Subclasses must implement this method.")

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
        result = self.process_task(task)
        if task.get('one_time'):
            self.tasks[:] = [t for t in self.tasks if t is not task]
        return result

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
            try:
                task: Task = self.task_queue.get(timeout = 1)
                result = self.finish_task(task)
                if result != 0:
                    self.app.add_to_transcript(f"Task {task['task_type']} failed with error code {result}.", "ERROR")
            except queue.Empty:
                pass
            except Exception as e:
                task_type = task.get('task_type', '?') if 'task' in locals() else '?'
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
        self.running = False
        self.thread.join()