"""participant management logic"""

from typing import Any

from _helper import send_sms, notify_coordinators
from _error_codes import code_prefix
from _types import App
from task_managers._task_manager import TaskManager, Task
import csv

# A participant is a small, loosely-structured dict parsed straight from
# participants.csv (see load_participants() below) -- kept as
# `dict[str, Any]` rather than a TypedDict/dataclass, matching Task's own
# convention in _task_manager.py.
Participant = dict[str, Any]

class ParticipantManager(TaskManager):
    def __init__(self, app: App, name: str = "ParticipantManager") -> None:
        try:
            super().__init__(app, name)
            self.survey_types = {
                'ema': 'ema_time',
                'ema_reminder': 'ema_reminder_time',
                'feedback': 'feedback_time',
                'feedback_reminder': 'feedback_reminder_time'
            }
            self.participants: list[Participant] = []
            self.file_path = self.app.participants_path
            self.load_participants()
        except Exception as e:
            self.app.add_to_transcript(f"Failed to initialize ParticipantManager: {e}", "ERROR")

    def load_participants(self) -> int:
        try:
            self.participants.clear()
            self.tasks.clear()
            with open(self.file_path, 'r') as file:
                lines = file.readlines()
        except Exception as e:
            self.app.add_to_transcript(f"Failed to load participants from CSV: {e}", "ERROR")
            return 1

        for row_number, line in enumerate(lines[1:], start = 2):
            if not line.strip():
                continue
            try:
                parts = line.strip().split(',')
                participant: Participant = {
                    'initials': parts[0].strip('"'),
                    'subid': parts[1].strip('"'),
                    'unique_id': parts[2].strip('"'),
                    'on_study': parts[3].strip('"').lower() == 'yes',
                    'phone_number': parts[4].strip('"'),
                    'ema_time': parts[5].strip('"'),
                    'ema_reminder_time': parts[6].strip('"'),
                    'feedback_time': parts[7].strip('"'),
                    'feedback_reminder_time': parts[8].strip('"')
                }
                self.participants.append(participant)
                self.schedule_participant_tasks(participant)
            except Exception as e:
                self.app.add_to_transcript(f"Skipping malformed participant row {row_number}: {e}", "ERROR")
        return 0
        
    def get_participant(self, unique_id: str) -> Participant | None:
        try:
            for participant in self.participants:
                if participant['unique_id'] == unique_id:
                    return participant
            self.app.add_to_transcript(f"Participant with ID {unique_id} not found.", "ERROR")
            return None
        except Exception as e:
            self.app.add_to_transcript(f"Failed to retrieve participant {unique_id}: {e}", "ERROR")
            return None
        
    def get_lapse_data_and_message(self, unique_id: str) -> dict[str, str]:
        """Stub -- always returns the same placeholder values regardless of
        `unique_id`; not yet wired to any real lapse-detection logic.
        """
        return {
            'lapse_level': 'high',
            'lapse_change': 'increasing',
            'most_important_feature': 'craving',
            'message': 'Sample message'
        }
    
    def get_participants(self) -> list[Participant]:
        try:
            return [
                {
                    'unique_id': participant['unique_id'],
                    'subid': participant['subid'],
                    'initials': participant['initials'],
                    'on_study': participant['on_study'],
                } for participant in self.participants
            ]
        except Exception as e:
            self.app.add_to_transcript(f"Failed to retrieve participants: {e}", "ERROR")
            return []

    def save_participants(self) -> int | None:
        try:
            with open(self.file_path, 'w') as file:
                file.write('"initials","subid","unique_id","on_study","phone_number","ema_time","ema_reminder_time","feedback_time","feedback_reminder_time"\n')
                for participant in self.participants:
                    on_study_str = 'yes' if participant['on_study'] else 'no'
                    file.write(f'"{participant["initials"]}","{participant["subid"]}","{participant["unique_id"]}","{on_study_str}","{participant["phone_number"]}","{participant["ema_time"]}","{participant["ema_reminder_time"]}","{participant["feedback_time"]}","{participant["feedback_reminder_time"]}"\n')
            return None
        except Exception as e:
            self.app.add_to_transcript(f"Failed to save participants to CSV: {e}", "ERROR")
            return 1
        
    def update_participant(self, unique_id: str, field: str, value: Any) -> int:
        try:
            participant = self.get_participant(unique_id)
            if participant:
                if field in participant:
                    if field == 'on_study':
                        if str(value).strip().lower() in ('true', 'yes'):
                            value = True
                        elif str(value).strip().lower() in ('false', 'no'):
                            value = False
                        else:
                            self.app.add_to_transcript(f"Invalid value '{value}' for on_study; expected true/false.", "ERROR")
                            return 1
                    participant[field] = value
                    self.save_participants()
                    for task_type, field_name in self.survey_types.items():
                        if field_name == field:
                            self.remove_task(task_type, participant_id = unique_id)
                            self.add_task(task_type, value, participant_id = unique_id)
                    self.app.add_to_transcript(f"Updated {field} for participant {unique_id} to {value}.", "INFO")
                    return 0
                else:
                    self.app.add_to_transcript(f"Field {field} does not exist for participant {unique_id}.", "ERROR")
                    return 1
            else:
                self.app.add_to_transcript(f"Failed to update participant {unique_id}: Participant not found.", "ERROR")
                return 1
        except Exception as e:
            self.app.add_to_transcript(f"An error occurred while updating participant {unique_id}: {e}", "ERROR")
            return 1
        
    def add_participant(self, participant: Participant) -> int:
        """Rolls back the in-memory append if save_participants() fails, so
        self.participants stays in sync with what's actually on disk.
        """
        self.participants.append(participant)
        if self.save_participants():
            self.participants.remove(participant)
            return 1
        self.schedule_participant_tasks(participant)
        return 0

    def schedule_participant_tasks(self, participant: Participant) -> None:
        for task_type, field_name in self.survey_types.items():
            task_time_str = participant.get(field_name)
            if task_time_str:
                self.add_task(task_type, task_time_str, participant_id = participant['unique_id'])

    def remove_participant(self, unique_id: str) -> int:
        participant = self.get_participant(unique_id)
        if participant:
            self.participants.remove(participant)
            self.save_participants()
            for task_type, field_name in self.survey_types.items():
                self.remove_task(task_type, participant_id = unique_id)
            self.app.add_to_transcript(f"Removed participant {unique_id}.", "INFO")
            return 0
        return 1
        
    def remove_task(self, task_type: str, task_time: str | None = None, participant_id: str | None = None) -> int:
        for task in self.tasks:
            if task['participant_id'] == participant_id and task['task_type'] == task_type:
                self.tasks.remove(task)
                self.app.add_to_transcript(f"Removed SMS task: {task_type} for participant {participant_id}", "INFO")
                return 0
        self.app.add_to_transcript(f"SMS task {task_type} for participant {participant_id} not found.", "ERROR")
        return 1
    
    def get_task_schedule(self) -> list[dict[str, Any]]:
        try:
            data: list[dict[str, Any]] = []
            for task in self.tasks:
                participant_id = task.get('participant_id')
                if participant_id is not None:
                    # get_participant() can return None (e.g. a task
                    # lingering for a since-removed participant); such a
                    # task can no longer run meaningfully, so it's excluded
                    # from the returned schedule rather than crashing this
                    # whole lookup (get_participant() itself already logs
                    # the "not found" error -- see process_task()'s
                    # equivalent handling of a missing participant).
                    participant = self.get_participant(participant_id)
                    if participant is None:
                        continue
                    on_study: Any = participant['on_study']
                else:
                    on_study = 'N/A'
                data.append({
                    "participant_id": task.get('participant_id', 'N/A'),
                    "on_study": on_study,
                    "task_type": task['task_type'],
                    "task_time": task['task_time'].strftime('%H:%M:%S'),
                    "run_today": task.get('run_today', False)
                })
            data.sort(key = lambda x: (x['participant_id'], x['task_time']))
            return data
        except Exception as e:
            self.app.add_to_transcript(f"Failed to retrieve system task schedule: {e}", "ERROR")
            return []
    
    def process_task(self, task: Task) -> int:
        try:
            participant_id = task.get('participant_id')
            if not participant_id:
                self.app.add_to_transcript("Participant ID is missing in SMS task.", "ERROR")
                return -1
            participant = self.get_participant(participant_id)
            if participant is None:
                self.app.add_to_transcript(f"Participant {participant_id} not found; skipping SMS task.", "ERROR")
                return -1
            # A recurring/scheduled task for an off-study participant is
            # silently skipped -- nobody's watching to confirm it, and the
            # whole point of turning off_study is to stop the automated
            # cadence. A one-time task is different: it only exists because
            # an RA deliberately triggered it right now (interface/API), and
            # (for the interface path -- see send_one_time_survey_menu)
            # already confirmed sending to an off-study participant
            # specifically, so it should go through rather than be silently
            # dropped here a second time.
            if participant['on_study'] is False and not task.get('one_time'):
                return 0
            # Default to "" (not a valid key in either task_column_map or
            # task_attr_map below) rather than None, purely so task_type has
            # a concrete `str` type -- behaviorally identical to the old
            # implicit-None case, since neither dict has "" as a key either.
            task_type: str = task.get('task_type', '')

            # reminder checking logic -- remind_ema/remind_feedback ("yes"/"no",
            # config/README.md's reminders.csv schema) record whether this
            # participant should still be reminded about that survey today;
            # "no" means they've already opened it, so skip the reminder.
            # Confirmed against main's original semantics -- the dev-branch
            # column-name fix (reading remind_ema/remind_feedback instead of
            # the nonexistent ema_opened/feedback_opened) was correct, but
            # the "yes" polarity check that landed alongside it was inverted.
            task_column_map = {
                "ema_reminder": "remind_ema",
                "feedback_reminder": "remind_feedback"
            }

            column_name = task_column_map.get(task_type)

            if column_name:
                with open(self.app.reminders_path, "r", newline="") as file:
                    reader = csv.DictReader(file)
                    for row in reader:
                        if row["unique_id"] == str(participant_id):
                            if row.get(column_name, "").strip().lower() == "no":
                                return 0  # Already opened
                            break

            participant_phone_number = participant['phone_number']
            self.app.add_to_transcript(f"Processing SMS task: {task_type} for participant {participant_id}", "INFO")
            # attribute names, not values -- looked up lazily below so an app
            # only configured for the task_type actually being processed
            # doesn't fail on an unrelated survey type's unset attribute.
            task_attr_map = {
                'ema': ('ema_survey_id', 'ema_message'),
                'ema_reminder': ('ema_survey_id', 'ema_reminder_message'),
                'feedback': ('feedback_survey_id', 'feedback_message'),
                'feedback_reminder': ('feedback_survey_id', 'feedback_reminder_message')
            }
            if task_type not in task_attr_map:
                self.app.add_to_transcript(f"Unknown SMS task type: {task_type}", "ERROR")
                return -1
            try:
                survey_id_attr, message_attr = task_attr_map[task_type]
                survey_id = getattr(self.app, survey_id_attr)
                message = getattr(self.app, message_attr)
                survey_link = f"https://uwmadison.co1.qualtrics.com/jfe/form/{survey_id}?Q_ExternalData={participant_id}"
                body = f"{message} {survey_link}"
            except Exception as e:
                self.app.add_to_transcript(f"Error parsing link: {e}", "ERROR")
                return -1
            try:
                if self.app.mode == "prod":
                    send_sms(self.app, [participant_phone_number], [body])
                self.app.add_to_transcript(f"SMS sent to {participant_id}.", "INFO")
                return 0
            except Exception as e:
                self.app.add_to_transcript(f"Failed to send SMS to {participant_id}: {e}", "ERROR")
                notify_coordinators(self.app, code_prefix('2001') + f"PRISM system failure: failed to send SMS to participant {participant_id}. Error: {e}")
                return -1
        except Exception as e:
            self.app.add_to_transcript(f"Error with sending a message: {e}", "ERROR")
            notify_coordinators(self.app, code_prefix('2002') + f"PRISM system failure: unexpected error while processing an SMS task. Error: {e}")
            return -1