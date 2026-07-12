"""extend this class to create system tasks"""

import random
from datetime import datetime
from _helper import notify_coordinators
from _error_codes import code_prefix
from _types import App

# kept in sync with run_prism.py's API_FIELD_DEFAULTS default for
# coordinator_alert_message -- used here too so a FakeApp/test app that
# hasn't loaded twilio.api still produces a sensible message.
DEFAULT_COORDINATOR_ALERT_MESSAGE = "{name}: {task_type} #{task_number} {outcome}. Script was executed at {task_start}."

class SystemTask:
    # Set as the first line of run() in every real subclass (CheckSystem,
    # RunRScript) before execute() below reads it -- declared here (type
    # only) rather than in __init__ since it genuinely doesn't exist yet at
    # construction time. execute()'s own except-clause below covers the one
    # case where run() raises before reaching that first line.
    task_type: str
    outcome: str

    def __init__(self, app: App) -> None:
        self.app = app
        self.task_number = str(random.randint(100000, 999999))
        self.task_start = datetime.now()

    def run(self) -> int:
        raise NotImplementedError("Subclasses must implement this method.")

    def execute(self) -> int:
        try:
            result: int | None = self.run()
        except Exception as e:
            # self.task_type is normally set as the first line of run() --
            # if run() raised before reaching it, fall back to the class
            # name so notify_via_sms()'s message still makes sense.
            if not hasattr(self, 'task_type'):
                self.task_type = self.__class__.__name__
            self.app.add_to_transcript(f"{self.task_type} #{self.task_number} raised an unhandled exception: {e}", "ERROR")
            result = 1
        self.outcome = "SUCCESS" if result == 0 else "FAILURE"
        self.app.add_to_transcript(f"{self.task_type} #{self.task_number} completed with status: {self.outcome}.", "INFO")
        if self.app.mode == "live":
            # Defensively wrapped: notify_via_sms() itself failing (Twilio
            # down, credentials broken, coordinators file unreadable, etc.)
            # must never propagate out of execute() -- this runs for every
            # task, success or failure, so an unguarded exception here would
            # crash whatever called execute() (the background scheduler
            # thread, if this ran off TaskManager.run()'s queue) over a
            # *notification* failure, not the task's own actual work.
            try:
                sms_result = self.notify_via_sms()
                if sms_result != 0:
                    self.app.add_to_transcript(f"Failed to send {sms_result} SMS notifications.", "ERROR")
            except Exception as e:
                self.app.add_to_transcript(f"Failed to send coordinator SMS notifications: {e}", "ERROR")
        return 1 if self.outcome == "FAILURE" else 0

    def notify_via_sms(self) -> int:
        alert_template = getattr(self.app, 'coordinator_alert_message', DEFAULT_COORDINATOR_ALERT_MESSAGE)
        task_start_str = self.task_start.strftime('%m/%d/%Y at %I:%M:%S %p')
        # Fill in every field except {name} -- notify_coordinators() fills
        # that in per-coordinator from study_coordinators_path. Passing
        # name='{name}' re-inserts the literal text "{name}" (str.format()
        # doesn't recursively re-parse a substituted value as a new format
        # field), so it survives as a placeholder for the second .format()
        # call inside notify_coordinators().
        message = alert_template.format(
            name='{name}',
            task_type=self.task_type,
            task_number=self.task_number,
            outcome=self.outcome,
            task_start=task_start_str,
        )
        # Only a FAILURE outcome is an error -- a SUCCESS message isn't a
        # failure and shouldn't carry an error code.
        if self.outcome == "FAILURE":
            message = code_prefix('1001') + message
        return notify_coordinators(self.app, message)