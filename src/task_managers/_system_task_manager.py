"""task management logic"""

import csv
import os
from datetime import datetime
from typing import Any

from task_managers._task_manager import TaskManager, Task
from system_tasks._system_task import SystemTask
from system_tasks._check_system import CheckSystem
from system_tasks._run_r_script import RunRScript
from _types import App

# Every system task, statically registered here. Adding a new task type
# means adding both a new system_tasks/_<name>.py file and a line here --
# there is no dynamic file-discovery/import mechanism, since PRISM only
# ever has one author for these files.
TASK_CLASSES: dict[str, type[SystemTask]] = {
    'CHECK_SYSTEM': CheckSystem,
    'RUN_R_SCRIPT': RunRScript,
}

# The documented on-disk schema for system_task_schedule.csv (config/
# README.md) -- deliberately excludes `one_time`/`participant_id`, which
# every task dict may carry (TaskManager.add_task) but which aren't part of
# this file's persisted format. Named here, once, so save_tasks() (write)
# and load_task_schedule() (read, via DictReader's header row) can't drift
# out of sync with each other the way they did before (see save_to_csv's
# docstring in _task_manager.py for the bug this fixes).
SCHEDULE_CSV_HEADERS = ['task_type', 'task_time', 'r_script_path', 'run_today']

class SystemTaskManager(TaskManager):
    def __init__(self, app: App, name: str = "SystemTaskManager") -> None:
        super().__init__(app, name)
        self.task_types = self.get_task_types()
        self.file_path = self.app.system_task_schedule_path
        self.load_task_schedule()

    def get_task_types(self) -> dict[str, str]:
        """task_type -> human-readable label (e.g. RUN_R_SCRIPT ->
        RunRScript), derived from TASK_CLASSES' keys. This dict is
        JSON-serialized over GET /system/get_task_types and displayed to
        RAs in the tasks menus, so values must stay plain strings, not the
        TASK_CLASSES class objects themselves.
        """
        return {
            task_type: task_type.replace('_', ' ').title().replace(' ', '')
            for task_type in TASK_CLASSES
        }

    def get_r_script_tasks(self) -> dict[str, str]:
        try:
            return {
                (f[:-2]): (f[:-2])
                for f in os.listdir(self.app.r_scripts_dir)
                if f.endswith('.R')
            }
        except Exception as e:
            self.app.add_to_transcript(f"Failed to list R scripts: {e}", "ERROR")
            return {}
    
    def load_task_schedule(self) -> None:
        """Uses csv.DictReader (maps by the file's own header row) rather
        than a naive line.split(',') + fixed-width positional unpack --
        immune both to an embedded comma corrupting every subsequent field,
        and to a column-count mismatch against the writer (save_tasks()),
        which used to crash this whole method with `UnboundLocalError:
        cannot access local variable 'task_type'` the moment the file
        picked up an extra column save_to_csv had silently started writing
        (see SCHEDULE_CSV_HEADERS/save_to_csv's docstring) -- task_type/
        task_time_str come from row.get(..., '') below, so they're always
        bound before the try block even for a malformed row.
        """
        with self._tasks_lock:
            self.tasks.clear()
            try:
                with open(self.file_path, 'r', newline = '') as file:
                    reader = csv.DictReader(file)
                    for row in reader:
                        task_type = (row.get('task_type') or '').strip()
                        task_time_str = (row.get('task_time') or '').strip()
                        if not task_type and not task_time_str:
                            continue  # blank line
                        try:
                            task_time = datetime.strptime(task_time_str, '%H:%M:%S').time()
                            if task_type not in self.task_types:
                                self.app.add_to_transcript(f"Unknown task type: {task_type}", "ERROR")
                                continue
                            self.add_task(task_type, task_time, r_script_path = row.get('r_script_path', ''))
                        except ValueError:
                            self.app.add_to_transcript(f"Invalid time format for task {task_type}: {task_time_str}", "ERROR")
                        except Exception as e:
                            self.app.add_to_transcript(f"Error scheduling task {task_type}: {e}", "ERROR")
                    self.tasks.sort(key = lambda x: x['task_time'])
            except FileNotFoundError:
                self.app.add_to_transcript(f"Task schedule file not found at: {self.file_path}", "ERROR")
            except Exception as e:
                self.app.add_to_transcript(f"An error occurred while loading the task schedule: {e}", "ERROR")

    def clear_schedule(self) -> None:
        with self._tasks_lock:
            self.tasks.clear()
        self.save_tasks()

    def get_task_schedule(self) -> list[dict[str, Any]]:
        try:
            with self._tasks_lock:
                return [
                    {
                        "task_type": task['task_type'],
                        "task_time": task['task_time'].strftime('%H:%M:%S'),
                        "r_script_path": task.get('r_script_path', ''),
                        "run_today": task.get('run_today', False)
                    } for task in self.tasks
                ]
        except Exception as e:
            self.app.add_to_transcript(f"Failed to retrieve system task schedule: {e}", "ERROR")
            return []

    def save_tasks(self) -> None:
        # Snapshot (a shallow copy) taken under the lock, then written
        # outside it -- file I/O should never happen while holding
        # _tasks_lock, even though this particular write is small/fast, to
        # keep the "never block other threads on I/O while holding this
        # lock" rule exception-free rather than "except when it's probably
        # fine".
        with self._tasks_lock:
            self.tasks.sort(key = lambda x: x['task_time'])
            snapshot = list(self.tasks)
        self.save_to_csv(snapshot, self.file_path, headers = SCHEDULE_CSV_HEADERS)

    def remove_task(
        self,
        task_type: str,
        task_time: str | None = None,
        participant_id: str | None = None,
        r_script_path: str | None = None,
    ) -> int:
        # task_time keeps the `= None` default for compatibility with the
        # original signature, but every current caller (_routes.py's
        # remove_system_task/remove_r_script_task) always supplies it; a
        # real None here would already fail inside strptime() at runtime
        # (TypeError) exactly as before -- this ignore doesn't change that.
        parsed_task_time = datetime.strptime(task_time, '%H:%M:%S').time()  # type: ignore[arg-type]
        with self._tasks_lock:
            for task in self.tasks:
                if task['task_type'] == task_type and task['task_time'] == parsed_task_time:
                    if r_script_path and task.get('r_script_path') != r_script_path:
                        continue
                    self.tasks.remove(task)
                    found = True
                    break
            else:
                found = False
        if found:
            self.save_tasks()
            self.app.add_to_transcript(f"Removed system task: {task_type} at {parsed_task_time.strftime('%H:%M:%S')}", "INFO")
            return 0
        self.app.add_to_transcript(f"Task {task_type} at {parsed_task_time.strftime('%H:%M:%S')} not found.", "ERROR")
        return 1

    def process_task(self, task: Task) -> int:
        """Looks up the task class directly from the static TASK_CLASSES
        registry -- an unrecognized task_type (e.g. a stale schedule-CSV
        row) just logs and returns -1; it isn't a coordinator-alert-worthy
        system failure the way an import error used to be, since a task
        type that doesn't exist here can never have run successfully
        before either.
        """
        # Default to "" (not a valid TASK_CLASSES key) rather than None,
        # purely so task_type has a concrete `str` type -- the `is None`
        # check right below behaves identically either way, since "" isn't
        # a registered task type any more than None is.
        task_type: str = task.get('task_type', '')
        self.app.add_to_transcript(f"Executing task: {task_type}", "INFO")
        task_class = TASK_CLASSES.get(task_type)
        if task_class is None:
            self.app.add_to_transcript(f"Unknown task type: {task_type}", "ERROR")
            return -1
        r_script_path = task.get('r_script_path')
        if r_script_path:
            # RunRScript.__init__ takes an extra r_script_path argument that
            # the common SystemTask base class (TASK_CLASSES' declared value
            # type) doesn't -- this branch only ever runs for the
            # 'RUN_R_SCRIPT' task_type, whose class is RunRScript, so the
            # extra argument is always valid at runtime even though the
            # static type of `task_class` (type[SystemTask]) can't express
            # per-key constructor signatures.
            result = task_class(self.app, r_script_path).execute()  # type: ignore[call-arg]
        else:
            result = task_class(self.app).execute()
        return result if result is not None else 0