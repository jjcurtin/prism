"""participant management logic"""

from datetime import date, datetime
from typing import Any

from _helper import is_valid_phone_number, send_sms, notify_coordinators
from _error_codes import code_prefix
from _types import App
from task_managers._task_manager import TaskManager, Task
import csv

# A participant is a small, loosely-structured dict parsed straight from
# participants.csv (see load_participants() below) -- kept as
# `dict[str, Any]` rather than a TypedDict/dataclass, matching Task's own
# convention in _task_manager.py.
Participant = dict[str, Any]

# The documented on-disk schema for study_participants.csv (config/
# README.md). Named once here so save_participants() (write) and
# load_participants() (read, via DictReader's header row) can't drift out
# of sync with each other -- same reasoning as SystemTaskManager's
# SCHEDULE_CSV_HEADERS.
PARTICIPANT_CSV_HEADERS = [
    'initials', 'subid', 'unique_id', 'on_study', 'phone_number',
    'ema_time', 'ema_reminder_time', 'feedback_time', 'feedback_reminder_time',
]

# update_participant()/add_participant() failure-reason codes -- distinct
# nonzero ints, not just "1" for every rejection reason. Found by an
# external adversarial review: the route mapped any nonzero
# update_participant() result to a generic 404 "Participant not found",
# so an existing participant's rejected unique_id edit, an invalid field
# value, and a genuinely missing participant were all indistinguishable
# to the API caller -- the manager logged the real reason server-side,
# but the HTTP response actively lied about it. Kept as plain ints (this
# file's existing 0/1/-1 convention throughout), not a new Enum/Literal
# type -- nothing else in this codebase does that, and a distinguishable
# int is the smallest change that fixes the actual bug. Every existing
# caller that only checks `!= 0` is unaffected; only _routes.py needs to
# switch on the specific value to report an honest status/message.
UPDATE_OK = 0
UPDATE_NOT_FOUND = 1
UPDATE_UNKNOWN_FIELD = 2
UPDATE_IMMUTABLE_FIELD = 3
UPDATE_INVALID_VALUE = 4
UPDATE_SAVE_FAILED = 5
UPDATE_UNEXPECTED_ERROR = 6

ADD_OK = 0
ADD_DUPLICATE_ID = 1
ADD_INVALID_VALUE = 2
ADD_SAVE_FAILED = 3

class ParticipantManager(TaskManager):
    """Invariants (see check_invariants() below for the executable form):

    I1. Every task in self.tasks with a participant_id references a
        participant currently present in self.participants (no orphans).
    I2. At most one recurring task per (task_type, participant_id) pair
        (no duplicates).
    I3. self.participants and its on-disk CSV agree after every mutation
        method (add/update/remove_participant) returns 0 -- never
        partially applied.
    I4. unique_id is immutable once a participant is added -- it's also
        referenced externally by Qualtrics Q_ExternalData and
        reminders.csv, which this app can't rewrite, so in-app re-keying
        would only fix half the picture anyway.
    """

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
            # Rate-limits the coordinator page in process_task() for a
            # broken reminders.csv to once/day -- see that method's own
            # comment for why the fail-open policy pages at all.
            self._last_reminders_failure_page_date: date | None = None
            # Reuses TaskManager.__init__'s _tasks_lock rather than a
            # second, separate lock -- self.participants and self.tasks are
            # frequently mutated together in the same logical operation
            # here (load_participants() clears both; remove_participant()
            # removes from participants then removes each of that
            # participant's tasks), and a single lock means there's no
            # lock-ordering to get wrong between two locks. Never held
            # across process_task()/send_sms() (the network call), same
            # rule as the base class.
            self.file_path = self.app.participants_path
            self.load_participants()
        except Exception as e:
            self.app.add_to_transcript(f"Failed to initialize ParticipantManager: {e}", "ERROR")

    def check_invariants(self) -> list[str]:
        """Executable form of the class-level invariants above. Not called
        anywhere in production code paths -- this is a test/dev-only tool
        for verifying I1-I3 hold after an arbitrary sequence of mutation
        calls (see tests/test_participant_manager.py's sequence test),
        since per-method tests alone can't catch a bug that only shows up
        after a specific *combination* of operations (the unique_id bug
        I4 exists to prevent was exactly this shape). Returns a list of
        human-readable violation descriptions, empty if everything holds.
        I4 isn't checked here since it's enforced unconditionally by
        update_participant rejecting the edit outright -- there's no
        reachable state where it could be violated to check for.
        """
        violations: list[str] = []
        with self._tasks_lock:
            participant_ids = {p['unique_id'] for p in self.participants}
            seen_recurring: set[tuple[str | None, str | None]] = set()
            for task in self.tasks:
                participant_id = task.get('participant_id')
                if participant_id is None:
                    continue
                if participant_id not in participant_ids:
                    violations.append(
                        f"I1 violated: task {task.get('task_type')!r} references participant "
                        f"{participant_id!r}, which is not in self.participants"
                    )
                if not task.get('one_time'):
                    key = (task.get('task_type'), participant_id)
                    if key in seen_recurring:
                        violations.append(f"I2 violated: duplicate recurring task {key}")
                    seen_recurring.add(key)
            try:
                with open(self.file_path, 'r', newline = '') as file:
                    on_disk_ids = {row.get('unique_id') for row in csv.DictReader(file)}
            except Exception:
                on_disk_ids = None
            if on_disk_ids is not None and on_disk_ids != participant_ids:
                violations.append(
                    f"I3 violated: self.participants ({sorted(participant_ids, key = str)}) doesn't "
                    f"match the on-disk CSV ({sorted(on_disk_ids, key = str)})"
                )
        return violations

    def load_participants(self) -> int:
        """Uses csv.DictReader (maps by the file's own header row) rather
        than a naive line.split(',') + strip('"') positional unpack --
        immune to an embedded comma or quote in a field corrupting every
        subsequent field, unlike the old parser.
        """
        with self._tasks_lock:
            try:
                self.participants.clear()
                self.tasks.clear()
                with open(self.file_path, 'r', newline = '') as file:
                    reader = csv.DictReader(file)
                    rows = list(reader)
            except Exception as e:
                self.app.add_to_transcript(f"Failed to load participants from CSV: {e}", "ERROR")
                return 1

            for row_number, row in enumerate(rows, start = 2):
                if not any((row.get(col) or '').strip() for col in PARTICIPANT_CSV_HEADERS):
                    continue  # blank line
                try:
                    participant: Participant = {
                        'initials': row.get('initials') or '',
                        'subid': row.get('subid') or '',
                        'unique_id': row.get('unique_id') or '',
                        'on_study': (row.get('on_study') or '').strip().lower() == 'yes',
                        'phone_number': row.get('phone_number') or '',
                        'ema_time': row.get('ema_time') or '',
                        'ema_reminder_time': row.get('ema_reminder_time') or '',
                        'feedback_time': row.get('feedback_time') or '',
                        'feedback_reminder_time': row.get('feedback_reminder_time') or '',
                    }
                    self.participants.append(participant)
                    self.schedule_participant_tasks(participant)
                except Exception as e:
                    self.app.add_to_transcript(f"Skipping malformed participant row {row_number}: {e}", "ERROR")
            return 0

    def get_participant(self, unique_id: str) -> Participant | None:
        try:
            with self._tasks_lock:
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
            with self._tasks_lock:
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

    def get_phone_numbers(self, on_study_only: bool) -> list[str]:
        """A safe, locked copy -- never a reference into self.participants
        itself, so a caller iterating the returned list can't race a
        concurrent load_participants()/add_participant()/remove_participant()
        mutating the underlying list mid-iteration. Routes should always go
        through this (or another locked accessor) rather than touching
        .participants directly.
        """
        with self._tasks_lock:
            if on_study_only:
                return [p['phone_number'] for p in self.participants if p['on_study']]
            return [p['phone_number'] for p in self.participants]

    def save_participants(self) -> int:
        """Returns 0 on success, 1 on failure -- same convention as every
        other mutation method in this class. (Used to return None on
        success, which happened to also be falsy and so "worked" at
        add_participant's `if self.save_participants():` call site, but was
        a landmine for remove_participant/update_participant, which called
        this and discarded the result entirely rather than getting it
        wrong -- see their own docstrings.)
        """
        # Snapshot taken under the lock, file write happens outside it --
        # same "never hold this lock across I/O" rule as
        # SystemTaskManager.save_tasks(), even though this write is small.
        with self._tasks_lock:
            snapshot = list(self.participants)
        try:
            with open(self.file_path, 'w', newline = '') as file:
                writer = csv.DictWriter(file, fieldnames = PARTICIPANT_CSV_HEADERS, quoting = csv.QUOTE_ALL)
                writer.writeheader()
                for participant in snapshot:
                    # Built from PARTICIPANT_CSV_HEADERS explicitly, not
                    # dict(participant) -- csv.DictWriter defaults to
                    # extrasaction='raise', so passing the participant dict
                    # through unfiltered would fail the entire write (a
                    # regression from the old writer's explicit
                    # participant["field"] access, which silently ignored
                    # any extra key) the moment a caller's dict carries a
                    # field this schema doesn't know about -- e.g. any API
                    # client that sends more than the 9 documented fields,
                    # not just the interface's own menu.
                    row = {header: participant.get(header, '') for header in PARTICIPANT_CSV_HEADERS}
                    row['on_study'] = 'yes' if participant['on_study'] else 'no'
                    writer.writerow(row)
            return 0
        except Exception as e:
            self.app.add_to_transcript(f"Failed to save participants to CSV: {e}", "ERROR")
            return 1

    def update_participant(self, unique_id: str, field: str, value: Any) -> int:
        """Enforces I4 (unique_id is immutable) and I3 (memory/disk agree
        after a 0 return) directly, rather than merely documenting them:
        a unique_id edit is rejected outright rather than attempted, and a
        save_participants() failure reverts the in-memory field change
        instead of leaving it applied only in memory.

        Returns one of the UPDATE_* codes above (module level), not a bare
        0/1 -- _routes.py's update_participant route switches on the
        specific value to report an honest status/message instead of
        collapsing every rejection reason into a generic 404.
        """
        try:
            # Locked as one unit: field mutation + persist + reschedule
            # must be atomic, not three independently-interleavable steps
            # -- get_participant()/save_participants()/remove_task()/
            # add_task() below all reacquire this same lock themselves
            # (it's an RLock, so that's safe from this same thread).
            with self._tasks_lock:
                if field == 'unique_id':
                    # Rejected rather than re-keyed in place: a rekey here
                    # would still leave self.tasks correctly pointed (that
                    # part's fixable), but unique_id is also the join key
                    # into Qualtrics Q_ExternalData and reminders.csv, which
                    # this app doesn't own and can't rewrite -- so an
                    # in-app rekey fixes only half the picture while
                    # looking like it fixed all of it. Remove-and-re-add is
                    # the safe path (see I4).
                    self.app.add_to_transcript(
                        f"Rejected attempt to edit unique_id for participant {unique_id}: unique_id is "
                        "immutable (also referenced by Qualtrics Q_ExternalData and reminders.csv, which "
                        "this app doesn't rewrite). Remove and re-add the participant instead.", "ERROR"
                    )
                    return UPDATE_IMMUTABLE_FIELD
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
                                return UPDATE_INVALID_VALUE
                        elif field in self.survey_types.values() and value:
                            # Validated up front, not left to add_task()'s
                            # strptime below -- found by an adversarial
                            # review of these invariants: the old code
                            # applied the field mutation and persisted it
                            # BEFORE reaching add_task(), so a bad time
                            # string (e.g. "", or any non-HH:MM:SS value)
                            # raised there, was caught by this method's own
                            # outer except, and reported failure (return 1)
                            # -- while the field had already been mutated
                            # and persisted, and the old task already
                            # removed. Validating first means a rejected
                            # edit changes nothing at all.
                            #
                            # value is normalized to the stripped form
                            # (not just validated against one) -- a
                            # sibling bug to the one already fixed for
                            # add_participant (e264b83): this used to
                            # validate a str(value).strip() copy but then
                            # persist/reschedule the UNSTRIPPED original,
                            # so a padded time (' 16:00:00 ') validated
                            # fine here but still raised, unstripped,
                            # inside add_task()'s own strptime call below
                            # -- after the field mutation and old-task
                            # removal had already gone through.
                            value = str(value).strip()
                            try:
                                datetime.strptime(value, '%H:%M:%S')
                            except ValueError:
                                self.app.add_to_transcript(
                                    f"Invalid time format '{value}' for {field}; expected HH:MM:SS.", "ERROR"
                                )
                                return UPDATE_INVALID_VALUE
                        elif field == 'phone_number' and value:
                            # Same normalize-before-validate-and-persist
                            # fix as the time-field branch above.
                            value = str(value).strip()
                            if value and not is_valid_phone_number(value):
                                self.app.add_to_transcript(
                                    f"Invalid phone_number '{value}' for participant {unique_id}; expected 10 digits.", "ERROR"
                                )
                                return UPDATE_INVALID_VALUE
                        old_value = participant[field]
                        participant[field] = value
                        if self.save_participants():
                            participant[field] = old_value  # roll back: mirror on-disk truth (I3)
                            self.app.add_to_transcript(
                                f"Failed to update participant {unique_id}: could not persist to CSV.", "ERROR"
                            )
                            return UPDATE_SAVE_FAILED
                        for task_type, field_name in self.survey_types.items():
                            if field_name == field:
                                self.remove_task(task_type, participant_id = unique_id)
                                # Matches schedule_participant_tasks' own
                                # semantics (only add_task for a non-empty
                                # time) -- clearing a survey time now
                                # removes that recurring task rather than
                                # trying to reschedule it for "".
                                if value:
                                    self.add_task(task_type, value, participant_id = unique_id)
                        self.app.add_to_transcript(f"Updated {field} for participant {unique_id} to {value}.", "INFO")
                        return UPDATE_OK
                    else:
                        self.app.add_to_transcript(f"Field {field} does not exist for participant {unique_id}.", "ERROR")
                        return UPDATE_UNKNOWN_FIELD
                else:
                    self.app.add_to_transcript(f"Failed to update participant {unique_id}: Participant not found.", "ERROR")
                    return UPDATE_NOT_FOUND
        except Exception as e:
            self.app.add_to_transcript(f"An error occurred while updating participant {unique_id}: {e}", "ERROR")
            return UPDATE_UNEXPECTED_ERROR

    def add_participant(self, participant: Participant) -> int:
        """Rejects a duplicate unique_id outright (found by an adversarial
        review of the invariants above, not the original audit: nothing
        upstream of this call -- not the route, not this method -- checked
        for an existing participant with the same id, so two
        add_participant() calls for the same unique_id used to silently
        produce two participants and two recurring tasks per shared
        survey_type, violating I2 and the spirit of I4 without ever
        touching update_participant's unique_id-edit rejection at all).

        Also validates each survey time field up front (found by an
        external adversarial review: this method had no validation of its
        own at all -- a malformed time string, e.g. "9am", used to persist
        the participant successfully via save_participants() and only then
        raise, uncaught, inside schedule_participant_tasks()'s add_task()
        call, propagating out of this method entirely. The caller (the
        route) saw an unhandled 500 and paged coordinators for what was
        actually a half-completed add: the participant record existed on
        disk with some or all of its recurring tasks never scheduled).
        update_participant already validates this same way; this mirrors
        it for the add path.

        Also coerces on_study to a real bool the same way (found in the
        same review: this method never coerced it at all, unlike
        update_participant. A JSON string "no" is truthy in Python, so
        save_participants()'s `'yes' if participant['on_study'] else
        'no'` wrote the literal string "yes" to disk -- the opposite of
        what the caller asked for -- and process_task()'s off-study skip
        (`participant['on_study'] is False`) also never matches a string,
        so an intentionally off-study participant kept receiving
        scheduled surveys. Not reachable through the shipped interface
        menu, which always sends a real bool via prompt_confirmation(),
        but a landmine for any other API caller).

        Also rolls back the in-memory append if save_participants() fails,
        so self.participants stays in sync with what's actually on disk.

        Returns one of the ADD_* codes above (module level), not a bare
        0/1 -- _routes.py's add_participant route switches on the specific
        value to report an honest status/message (a duplicate id is a 409,
        not the same generic 500 as a real disk-write failure).
        """
        with self._tasks_lock:
            # A direct existence check, not get_participant() -- that logs
            # an ERROR line for "not found", which is the expected, common
            # outcome here (most add_participant calls are for a genuinely
            # new id), not a real error worth alarming on.
            if any(p['unique_id'] == participant['unique_id'] for p in self.participants):
                self.app.add_to_transcript(
                    f"Rejected add_participant: unique_id {participant['unique_id']} already exists.", "ERROR"
                )
                return ADD_DUPLICATE_ID
            if 'on_study' in participant:
                # Same coercion as update_participant's on_study branch --
                # mutated in place so both save_participants() and the
                # in-memory off-study skip check (process_task) see a real
                # bool, not whatever JSON type the caller happened to send.
                # A real Python bool already round-trips through this same
                # check (str(True).lower() == 'true'), so no separate
                # isinstance case is needed.
                on_study_str = str(participant['on_study']).strip().lower()
                if on_study_str in ('true', 'yes'):
                    participant['on_study'] = True
                elif on_study_str in ('false', 'no'):
                    participant['on_study'] = False
                else:
                    self.app.add_to_transcript(
                        f"Rejected add_participant: invalid value '{participant['on_study']}' for on_study; "
                        "expected true/false.", "ERROR"
                    )
                    return ADD_INVALID_VALUE
            for field_name in self.survey_types.values():
                task_time_str = participant.get(field_name)
                if task_time_str:
                    # Normalized in place (not just validated against a
                    # copy) -- same strip-before-persist fix as
                    # update_participant's equivalent branch, so
                    # schedule_participant_tasks()'s own add_task() call
                    # below sees the same stripped value this check just
                    # validated, not a padded original that could still
                    # raise there.
                    task_time_str = str(task_time_str).strip()
                    participant[field_name] = task_time_str
                    try:
                        datetime.strptime(task_time_str, '%H:%M:%S')
                    except ValueError:
                        self.app.add_to_transcript(
                            f"Rejected add_participant: invalid time format '{task_time_str}' for {field_name}; "
                            "expected HH:MM:SS.", "ERROR"
                        )
                        return ADD_INVALID_VALUE
            self.participants.append(participant)
            if self.save_participants():
                self.participants.remove(participant)
                return ADD_SAVE_FAILED
            self.schedule_participant_tasks(participant)
            return ADD_OK

    def schedule_participant_tasks(self, participant: Participant) -> None:
        for task_type, field_name in self.survey_types.items():
            task_time_str = participant.get(field_name)
            if task_time_str:
                self.add_task(task_type, task_time_str, participant_id = participant['unique_id'])

    def remove_participant(self, unique_id: str) -> int:
        """Mirrors add_participant's rollback: if the removal can't be
        persisted, the in-memory list is restored and this participant's
        tasks are left alone, so memory and disk stay in agreement (I3)
        instead of a "removed" participant reappearing on the next reload
        while their tasks are already gone.
        """
        with self._tasks_lock:
            participant = self.get_participant(unique_id)
            if participant is None:
                return 1
            self.participants.remove(participant)
            if self.save_participants():
                self.participants.append(participant)  # roll back: mirror on-disk truth (I3)
                self.app.add_to_transcript(
                    f"Failed to remove participant {unique_id}: could not persist to CSV.", "ERROR"
                )
                return 1
            for task_type, field_name in self.survey_types.items():
                self.remove_task(task_type, participant_id = unique_id)
            self.app.add_to_transcript(f"Removed participant {unique_id}.", "INFO")
            return 0

    def remove_task(self, task_type: str, task_time: str | None = None, participant_id: str | None = None) -> int:
        with self._tasks_lock:
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
            with self._tasks_lock:
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

    def _maybe_page_reminders_csv_failure(self) -> None:
        """Pages coordinators about a broken reminders.csv at most once per
        calendar day -- process_task() calls this on every single reminder
        task it processes while the file stays broken (potentially many
        times a day across participants), and paging on every occurrence
        would just be alert-fatigue noise for a condition that's already
        being fixed or not.
        """
        today = self._now().date()
        if self._last_reminders_failure_page_date == today:
            return
        self._last_reminders_failure_page_date = today
        try:
            notify_coordinators(
                self.app,
                code_prefix('2003') + "PRISM system failure: reminders.csv is missing or unreadable; "
                "reminder-suppression checks are being skipped (participants may get a duplicate "
                "reminder) until this is fixed."
            )
        except Exception as notify_error:
            self.app.add_to_transcript(f"Also failed to notify coordinators about that error: {notify_error}", "ERROR")

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
                # Isolated in its own try/except, not the method-wide one
                # below -- this is a deliberate fail-OPEN policy, not a
                # missing try/except. A missing/unreadable/malformed
                # reminders.csv means this gate can't be evaluated one way
                # or the other; the choice of what to do then is a policy
                # decision (suppress the reminder, or send it anyway), not
                # an implementation detail to fall out of whichever branch
                # an exception happens to unwind into. Landed here fail-open
                # -- on failure, log and send the reminder anyway -- because
                # a duplicate reminder is recoverable (the participant gets
                # texted twice) while a wrongly-suppressed one is data loss
                # (they never get texted, and nothing else notices). The
                # suppression logic itself, when the file IS readable, is
                # unaffected and unchanged.
                try:
                    with open(self.app.reminders_path, "r", newline="") as file:
                        reader = csv.DictReader(file)
                        for row in reader:
                            if row["unique_id"] == str(participant_id):
                                if row.get(column_name, "").strip().lower() == "no":
                                    return 0  # Already opened
                                break
                except Exception as e:
                    self.app.add_to_transcript(
                        f"Could not read reminders.csv to check {column_name} for participant "
                        f"{participant_id}; sending the reminder anyway (fail-open). Error: {e}", "WARNING"
                    )
                    self._maybe_page_reminders_csv_failure()

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
                    # send_sms() communicates a per-recipient failure by
                    # RETURN COUNT, not by raising -- it catches
                    # TwilioRestException (and any other exception)
                    # internally per-recipient and only ever returns an
                    # int (see its own docstring). The old code called it
                    # and discarded that return value entirely, then
                    # unconditionally logged "SMS sent" and returned 0 --
                    # so a real Twilio failure (expired credential,
                    # blocked number, an outage) never raised here, this
                    # method reported success regardless, and the
                    # coordinator-alert code below it was unreachable for
                    # the exact failure mode it exists to catch. Found by
                    # an external adversarial review.
                    failed_count = send_sms(self.app, [participant_phone_number], [body])
                    if failed_count:
                        raise RuntimeError(
                            f"send_sms reported {failed_count} of 1 recipient(s) failed"
                        )
                    self.app.add_to_transcript(f"SMS sent to {participant_id}.", "INFO")
                else:
                    # Distinct from the real "SMS sent" line above -- the
                    # old code logged the same "SMS sent" text here too,
                    # even though no send is attempted in test mode, so
                    # the transcript couldn't distinguish a real send from
                    # a simulated one.
                    self.app.add_to_transcript(f"Simulated SMS send to {participant_id} (test mode).", "INFO")
                return 0
            except Exception as e:
                self.app.add_to_transcript(f"Failed to send SMS to {participant_id}: {e}", "ERROR")
                # Defensively wrapped: a notify_coordinators() failure here
                # (its own send_sms() call failing for whatever reason)
                # must never propagate out of process_task -- this runs on
                # the background scheduler thread via finish_task()/run(),
                # and an uncaught exception here over a failed *alert about*
                # a failure is exactly the cascade that used to silently
                # kill that thread the first time anything went wrong.
                try:
                    notify_coordinators(self.app, code_prefix('2001') + f"PRISM system failure: failed to send SMS to participant {participant_id}. Error: {e}")
                except Exception as notify_error:
                    self.app.add_to_transcript(f"Also failed to notify coordinators about that error: {notify_error}", "ERROR")
                return -1
        except Exception as e:
            self.app.add_to_transcript(f"Error with sending a message: {e}", "ERROR")
            try:
                notify_coordinators(self.app, code_prefix('2002') + f"PRISM system failure: unexpected error while processing an SMS task. Error: {e}")
            except Exception as notify_error:
                self.app.add_to_transcript(f"Also failed to notify coordinators about that error: {notify_error}", "ERROR")
            return -1