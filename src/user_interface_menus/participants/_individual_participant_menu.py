"""menu for managing an individual participant"""

import time
from typing import Any

from user_interface_menus.utils._menu_display import *
from user_interface_menus._menu_helper import *
from user_interface_menus._types import Interface, MenuOptions

def individual_participant_menu(self: Interface, participant_id: str) -> None:
    def remove_participant_menu(self: Interface) -> int | None:
        if prompt_confirmation(self, prompt = "Remove participant?"):
            ok, _ = self.api("DELETE", f"participants/remove_participant/{participant_id}")
            if ok:
                success("Participant removed.", self)
                return 1
            else:
                error("Failed to remove participant.", self)
                return 0
        return None

    def update_field_menu(self: Interface, choice: str) -> None:
        # No '3'/unique_id entry -- unique_id is immutable (see
        # ParticipantManager's I4 invariant and update_participant's
        # rejection of unique_id edits); remove-and-re-add is the only
        # supported way to change it. Not renumbered around the gap so
        # every other key stays stable across this change.
        field_map = {
            '1': 'initials', '2': 'subid', '4': 'on_study',
            '5': 'phone_number', '6': 'ema_time', '7': 'ema_reminder_time',
            '8': 'feedback_time', '9': 'feedback_reminder_time'
        }
        field = field_map[choice]
        new_val = get_input(self, prompt = f"Enter new value for {field}: ")

        if field == 'on_study':
            if new_val.lower() in ['true', 'True', 't', 'T']:
                new_val = "True"
            elif new_val.lower() in ['false', 'False', 'f', 'F']:
                new_val = "False"
            else:
                error("Invalid input for on_study. Please enter 'True' or 'False'.")
                return
        elif field in ['ema_time', 'ema_reminder_time', 'feedback_time', 'feedback_reminder_time']:
            try:
                time.strptime(new_val, '%H:%M:%S')
            except ValueError:
                error(f"Invalid time format for {field}. Please use HH:MM:SS format.")
                return
        elif field == 'subid':
            if not new_val.isnumeric():
                error("Sub ID must be a number.")
                return
        elif field == 'phone_number':
            if new_val and not PHONE_NUMBER_RE.fullmatch(new_val):
                error("Phone number must be exactly 10 digits.")
                return

        ok, _ = self.api("PUT", f"participants/update_participant/{participant_id}/{field}/{new_val}")
        if ok:
            participant[field] = new_val
            success("Participant updated.", self)
        else:
            error("Failed to update participant.", self)

    def send_one_time_survey_menu(self: Interface, participant_id: str, survey_type: str) -> None:
        """Sends a single one-off ema/feedback survey to this participant
        right now (POST /participants/send_survey/<id>/<survey_type>, fixed
        to `survey_type` -- no type-prompting). The route sends
        synchronously and returns the real outcome, so `ok` here reflects
        whether the SMS actually went out, not just whether a task was
        queued.

        An off-study participant still gets the real, personalized survey
        link -- same as an on-study participant -- but only after an extra,
        specific confirmation naming that fact, replacing the generic
        confirmation rather than stacking both. process_task's own
        recurring-task off-study skip (_participant_manager.py) doesn't
        apply here since this is a one-time task, deliberately triggered
        and (for this path) already confirmed right here.

        `participant['on_study']` isn't consistently typed: freshly fetched
        from the API it's a real bool (JSON round-trip), but
        update_field_menu above stores a live edit back as the string
        "True"/"False" instead -- so this checks both representations
        rather than `is False`, which would silently miss an off-study
        participant right after their on_study field was just toggled in
        this same session.
        """
        on_study_value = participant.get('on_study')
        off_study = on_study_value is False or (
            isinstance(on_study_value, str) and on_study_value.strip().lower() == 'false'
        )
        if off_study:
            prompt = f"Participant is not on study. Send {survey_type} survey anyway?"
        else:
            prompt = f"Send a one-time {survey_type} survey now?"
        if not prompt_confirmation(self, prompt = prompt):
            return
        ok, _ = self.api("POST", f"participants/send_survey/{participant_id}/{survey_type}")
        if ok:
            success(f"{survey_type.capitalize()} survey sent.", self)
        else:
            error(f"Failed to send {survey_type} survey.", self)

    def send_message_menu(self: Interface, participant_id: str) -> None:
        message = print_twilio_terminal_prompt()
        if not message:
            error("Message cannot be empty.")
            return
        ok, _ = self.api("POST", f"participants/send_custom_sms/{participant_id}", json={"message": message})
        if ok:
            success("Message sent.", self)
        else:
            error("Failed to send message.", self)

    ok, data = self.api("GET", f"participants/get_participant/{participant_id}")
    # A separate, Optional-typed local for the raw lookup, narrowed into
    # `participant` (declared non-Optional) right below -- kept as two
    # names, not one reassigned/narrowed variable, because mypy doesn't
    # carry flow-sensitive narrowing into the nested closures above (they
    # close over `participant` by name, not by the value it holds at
    # closure-definition time), so a narrowed-in-place `participant: X |
    # None` would still type-check as Optional inside them.
    fetched_participant: dict[str, Any] | None = data.get("participant") if ok and data else None
    if not fetched_participant:
        error("Failed to retrieve participant schedule.")
        return
    participant: dict[str, Any] = fetched_participant

    while True:
        # menu options are redefined on each iteration to reflect current participant data
        menu_options: MenuOptions = {
            '1': {'description': f'initials: {participant.get('initials')}', 'menu_caller': lambda self: update_field_menu(self, '1')},
            '2': {'description': f'subid: {participant.get('subid')}', 'menu_caller': lambda self: update_field_menu(self, '2')},
            '4': {'description': f'on_study: {participant.get('on_study')}', 'menu_caller': lambda self: update_field_menu(self, '4')},
            '5': {'description': f'phone_number: {participant.get('phone_number')}', 'menu_caller': lambda self: update_field_menu(self, '5')},
            '6': {'description': f'ema_time: {participant.get('ema_time')}', 'menu_caller': lambda self: update_field_menu(self, '6')},
            '7': {'description': f'ema_reminder_time: {participant.get('ema_reminder_time')}', 'menu_caller': lambda self: update_field_menu(self, '7')},
            '8': {'description': f'feedback_time: {participant.get('feedback_time')}', 'menu_caller': lambda self: update_field_menu(self, '8')},
            '9': {'description': f'feedback_reminder_time: {participant.get('feedback_reminder_time')}', 'menu_caller': lambda self: update_field_menu(self, '9')},
            'remove': {'description': 'Remove Participant', 'menu_caller': lambda self: remove_participant_menu(self)},
            'ema': {'description': 'Send One-Time EMA Survey', 'menu_caller': lambda self: send_one_time_survey_menu(self, participant_id, 'ema')},
            'feedback': {'description': 'Send One-Time Feedback Survey', 'menu_caller': lambda self: send_one_time_survey_menu(self, participant_id, 'feedback')},
            'message': {'description': 'Send Message', 'menu_caller': lambda self: send_message_menu(self, participant_id)}
        }
        if not self.commands_queue:
            print_menu_header(f"Participant ID {participant_id} Info")
            assistant_header_write(self, ["Enter an index to update a field, or, choose another option."])
        print_dashes()
        if print_menu_options(self, menu_options, submenu = True, index_and_text = True):
            break
