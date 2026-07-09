# extend this class to create system tasks

import random
from datetime import datetime
from _helper import send_sms

class SystemTask:
    def __init__(self, app):
        self.app = app
        self.task_number = str(random.randint(100000, 999999))
        self.task_start = datetime.now()

    def execute(self):
        try:
            result = self.run()
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
        if self.app.mode == "prod":
            sms_result = self.notify_via_sms()
            if sms_result != 0:
                self.app.add_to_transcript(f"Failed to send {sms_result} SMS notifications.", "ERROR")
        return 1 if self.outcome == "FAILURE" else 0

    def notify_via_sms(self):
        try:
            with open(self.app.study_coordinators_path, 'r') as f:
                lines = f.readlines()
                lines = lines[1:]
        except FileNotFoundError:
            self.app.add_to_transcript("No study coordinators found. SMS notifications will not be sent.", "WARNING")
            return 1
        except Exception as e:
            self.app.add_to_transcript(f"Failed to read study coordinators. Error message: {e}", "ERROR")
            return 1

        phone_numbers = []
        bodies = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                name, phone_number = line.split(',')
                name = name.strip('"')
                phone_number = phone_number.strip('"')
                if phone_number and phone_number != "":
                    body = f"{name}: {self.task_type} #{self.task_number} {self.outcome}. Script was executed at {self.task_start.strftime('%m/%d/%Y at %I:%M:%S %p')}."
                    phone_numbers.append(phone_number)
                    bodies.append(body)
            except Exception as e:
                self.app.add_to_transcript(f"Skipping malformed study coordinator entry: {e}", "ERROR")

        if not phone_numbers:
            return 0

        return send_sms(self.app, phone_numbers, bodies)