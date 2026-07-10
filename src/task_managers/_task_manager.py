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

    def add_task(self, task_type, task_time, r_script_path = None, participant_id = None):
        """`r_script_path` accepts the literal string "None" as an
        empty/none value in addition to "". Callers that pass this through a
        URL path segment (e.g. _routes.py's add_system_task route) can't
        encode a truly empty string there, so they send the literal "None"
        instead.
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
        if participant_id is not None:
            task_dict['participant_id'] = participant_id
        self.tasks.append(task_dict)  
    
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
    
    def run(self):
        while self.running:
            self.check_tasks()
            try:
                task = self.task_queue.get(timeout = 1)
                result = self.process_task(task)
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