"""base class for task managers"""

import queue
import threading
from datetime import datetime

from _helper import notify_coordinators
from _error_codes import code_prefix

class TaskManager():
    def __init__(self, app, name):
        self.app = app
        self.name = name
        self.running = True
        self.tasks = []
        self.task_queue = queue.Queue()
        self.thread = threading.Thread(target = self.run)
        self.thread.start()

    def add_task(self, task_type, task_time, r_script_path = None, participant_id = None, one_time = False):
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

        Returns the created task dict so a caller that needs to process it
        synchronously (see `finish_task`) can reference this exact task
        instance later, rather than re-looking it up by task_type +
        participant_id -- which could otherwise ambiguously match a
        different, unrelated task sharing the same type/participant (e.g. a
        one-time 'ema' send and a participant's recurring daily 'ema'
        task).
        """
        task_dict = {
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
        self.tasks.append(task_dict)
        return task_dict
    
    def save_to_csv(self, data, file_path):
        try:
            headers = data[0].keys() if data else []
            with open(file_path, 'w') as f:
                f.write(','.join(f'"{header}"' for header in headers) + '\n')
                for row in data:
                    f.write(','.join(f'"{str(row[header])}"' for header in headers) + '\n')
        except Exception as e:
            self.app.add_to_transcript(f"Failed to save data to CSV at {file_path}: {e}", "ERROR")

    def check_tasks(self):
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

    def process_task(self, task):
        raise NotImplementedError("Subclasses must implement this method.")

    def finish_task(self, task):
        """Process `task` and, if it's flagged `one_time`, remove it from
        self.tasks immediately afterward -- regardless of whether
        process_task succeeded or failed, and with no retry. This is the
        single place one-time cleanup happens, shared by both the normal
        polling loop below (`run()`) and any direct/manual invocation (e.g.
        a route that needs a synchronous result right now instead of
        waiting for the next `check_tasks` tick) -- so a one-time task's
        lifecycle is identical no matter which path finishes it.

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

    def run(self):
        while self.running:
            self.check_tasks()
            try:
                task = self.task_queue.get(timeout = 1)
                result = self.finish_task(task)
                if result != 0:
                    self.app.add_to_transcript(f"Task {task['task_type']} failed with error code {result}.", "ERROR")
            except queue.Empty:
                pass
            except Exception as e:
                task_type = task.get('task_type', '?') if 'task' in locals() else '?'
                self.app.add_to_transcript(f"An error occurred while processing task {task_type}: {e}", "ERROR")
                notify_coordinators(self.app, code_prefix('3001') + f"PRISM system failure: an error occurred while processing task {task_type} in {self.name}. Error: {e}")
                # note: changed print to add_to_transcript and removed the thing that kills the manager
        self.app.add_to_transcript(f"{self.name} processor stopped.", "INFO")

    def stop(self):
        self.running = False
        self.thread.join()