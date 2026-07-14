"""participant management menus"""

from typing import Any

from user_interface_menus._menu_helper import *
from user_interface_menus.participants._individual_participant_menu import individual_participant_menu
from user_interface_menus.participants._add_participant_menu import add_participant_menu
from user_interface_menus._types import Interface, MenuOptions

def refresh_participants_menu(self: Interface) -> None:
    if prompt_confirmation(self, prompt = "Refresh participants from CSV?"):
        ok, _ = self.api("POST", "participants/refresh_participants")
        if ok:
            success("Participants refreshed from CSV.", self)
        else:
            error("Failed to refresh participants.", self)
    else:
        success("Refresh cancelled.", self)

def send_announcement_menu(self: Interface) -> None:
    require_on_study = prompt_confirmation(self, prompt = "Send to participants on study only?", default_value = "y")
    print("Sending to participants on study only." if require_on_study else "Sending to all participants.")
    message = print_twilio_terminal_prompt()
    if not message:
        error("Message cannot be empty. Please try again.", self)
        return
    
    require_on_study_param = "yes" if require_on_study else "no"
    ok, _ = self.api(
        "POST", f"participants/study_announcement/{url_segment(require_on_study_param)}", json = {"message": message}
    )
    if ok:
        success("Study announcement sent.", self)
    else:
        error("No participants found or failed to retrieve.", self)

def send_studywide_ema_menu(self: Interface) -> None:
    require_on_study = prompt_confirmation(self, prompt = "Send to participants on study only?", default_value = "y")
    print("Sending to participants on study only." if require_on_study else "Sending to all participants.")
    require_on_study_param = "yes" if require_on_study else "no"
    ok, _ = self.api("POST", f"participants/send_studywide_survey/ema/{url_segment(require_on_study_param)}")
    if ok:
        # The send itself now runs on a background thread server-side and
        # this 202 response only confirms it started, not that it finished
        # -- see GET participants/studywide_survey_status for progress.
        success("Studywide EMA send started; check studywide_survey_status for progress.", self)
    else:
        error("Failed to start studywide EMA send (no participants found, or one is already in progress).", self)

def send_studywide_feedback_menu(self: Interface) -> None:
    require_on_study = prompt_confirmation(self, prompt = "Send to participants on study only?", default_value = "y")
    print("Sending to participants on study only." if require_on_study else "Sending to all participants.")
    require_on_study_param = "yes" if require_on_study else "no"
    ok, _ = self.api("POST", f"participants/send_studywide_survey/feedback/{url_segment(require_on_study_param)}")
    if ok:
        success("Studywide feedback send started; check studywide_survey_status for progress.", self)
    else:
        error("Failed to start studywide feedback send (no participants found, or one is already in progress).", self)

def ema_on_menu(self: Interface) -> None:
    ok, _ = self.api("POST", "participants/ema_on")
    if ok:
        success("EMA sends resumed for today.", self)
    else:
        error("Failed to resume EMA sends.", self)

def ema_off_menu(self: Interface) -> None:
    ok, _ = self.api("POST", "participants/ema_off")
    if ok:
        success("EMA sends paused for the rest of today.", self)
    else:
        error("Failed to pause EMA sends.", self)

def feedback_on_menu(self: Interface) -> None:
    ok, _ = self.api("POST", "participants/feedback_on")
    if ok:
        success("Feedback sends resumed for today.", self)
    else:
        error("Failed to resume feedback sends.", self)

def feedback_off_menu(self: Interface) -> None:
    ok, _ = self.api("POST", "participants/feedback_off")
    if ok:
        success("Feedback sends paused for the rest of today.", self)
    else:
        error("Failed to pause feedback sends.", self)

def next_participants_page_menu(self: Interface) -> None:
    # Only ever offered (see participant_management_menu's menu_options
    # wiring) when a further page genuinely exists -- but clamped again
    # against the real participant count on the next redraw regardless,
    # since self.participant_page_offset persists across redraws (same
    # convention as participant_display_mode/participant_filter_settings)
    # and a filter/refresh between redraws could shrink the list.
    self.participant_page_offset = getattr(self, 'participant_page_offset', 0) + ui_state.window_height

def previous_participants_page_menu(self: Interface) -> None:
    self.participant_page_offset = max(0, getattr(self, 'participant_page_offset', 0) - ui_state.window_height)

def remove_participant_menu(self: Interface) -> int | None:
    participant_id = get_input(self, prompt = "Please enter the unique ID of the participant that you would like to remove: ")
    if not participant_id or participant_id.strip() == '':
        error("Participant ID cannot be empty.")
        return 0
    if prompt_confirmation(self, prompt = f"Are you sure you want to remove participant with ID '{participant_id}'?"):
        ok, _ = self.api("DELETE", f"participants/remove_participant/{url_segment(participant_id)}")
        if ok:
            success("Participant removed.", self)
            return 1
        else:
            error("Failed to remove participant. Unique ID not found", self)
            return 0
    return None

def participant_management_menu(self: Interface) -> None:
    def print_task_schedule(self: Interface) -> None:
        if not self.commands_queue:
            tasks_ok, tasks = self.api("GET", "participants/get_participant_task_schedule")
            # get_participant_task_schedule now returns 200 with an empty
            # {"tasks": []} for "no tasks" (previously 404) -- so the outer
            # `tasks_ok and tasks` truthiness check alone would now print
            # an empty header and pause for Enter even when there's
            # nothing to show. Check the nested list instead, matching
            # every other "empty means nothing to display" call site.
            if tasks_ok and tasks and tasks.get("tasks"):
                print("Participant Task Schedule:")
                for task in tasks["tasks"]:
                    print(f"{task['participant_id']}: {task['task_type']} at {task['task_time']} - On Study: {task['on_study']}")
                exit_menu()

    def _sort(participants: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.participant_display_mode == "name":
            return sorted(participants, key = lambda x: (x['subid'].lower(), x['initials'].lower()))
        elif self.participant_display_mode == "unique_id":
            return sorted(participants, key = lambda x: int(x['unique_id']))
        elif self.participant_display_mode == "subid":
            # numeric, not lexicographic -- subid is validated as numeric on
            # both add (_add_participant_menu.py) and update
            # (update_field_menu's isnumeric() check), same as unique_id
            # above, so int() is always safe here.
            return sorted(participants, key = lambda x: int(x['subid']))
        elif self.participant_display_mode == "on_study":
            on_study_true = sorted([p for p in participants if p['on_study']], key = lambda x: int(x['unique_id']))
            on_study_false = sorted([p for p in participants if not p['on_study']], key = lambda x: int(x['unique_id']))
            return on_study_true + on_study_false
        else:
            return participants

    def change_display_mode(self: Interface) -> None:
        modes = ["name", "unique_id", "subid", "on_study"]
        print("Select display mode:")
        for mode in modes:
            print(f"{yellow(mode)}")
        print("Current mode:", red(self.participant_display_mode))
        choice = get_input(self, prompt = "Enter the mode you'd like to change to: ")
        if choice in modes:
            self.participant_display_mode = choice
            success(f"Display mode changed to {self.participant_display_mode}.", self)
        else:
            error("Invalid mode selected.", self)

    def _filter(participants: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.participant_filter_settings:
            return participants
        filtered = []
        for p in participants:
            if self.participant_filter_settings.get('on_study', 'All') == "All" or \
               (self.participant_filter_settings.get('on_study', 'All') == "True" and p['on_study']) or \
               (self.participant_filter_settings.get('on_study', 'All') == "False" and not p['on_study']):
                filtered.append(p)
        return filtered

    def _print_participant_table(page: list[dict[str, Any]]) -> None:
        # Spreadsheet-style, one row per participant (like the underlying
        # CSV) -- requested directly, replacing the old 3-column grid
        # layout, which buried participants in side-by-side columns
        # instead of a single scannable list.
        columns = [
            ("SUBID", "subid", 10), ("INITIALS", "initials", 10),
            ("UNIQUE_ID", "unique_id", 11), ("ON_STUDY", "on_study", 10),
            ("PHONE_NUMBER", "phone_number", 14),
        ]
        header = "".join(f"{name:<{width}}" for name, _, width in columns)
        print(yellow(header))
        print_dashes()
        for p in page:
            row = "".join(
                f"{('yes' if p[field] else 'no') if field == 'on_study' else p[field]:<{width}}"
                for _, field, width in columns
            )
            print(row)

    def filter_participants_menu(self: Interface) -> None:
        print("Current filter settings:")
        for key, value in self.participant_filter_settings.items():
            print(f"{key}: {value}")
        print("Available filters: on_study")
        filter_choice = get_input(self, prompt = "Enter filter to change: ")
        if filter_choice == '':
            return
        elif filter_choice not in self.participant_filter_settings:
            error(f"Invalid filter choice: {filter_choice}. Available filters: {', '.join(self.participant_filter_settings.keys())}", self)
            return
        new_value = get_input(self, prompt = f"Enter new value for {filter_choice} (True/False/All): ")
        if new_value not in ['True', 'False', 'All']:
            error("Invalid value. Please enter 'True', 'False', or 'All'.", self)
            return
        self.participant_filter_settings[filter_choice] = new_value
        success(f"Filter {filter_choice} set to {new_value}.", self)
        
    try:
        self.participant_display_mode = getattr(self, 'participant_display_mode', 'unique_id')
        if not self.participant_display_mode:
            self.participant_display_mode = 'unique_id'
        self.participant_filter_settings = getattr(self, 'participant_filter_settings', {})
        if not self.participant_filter_settings:
            self.participant_filter_settings = {
                'on_study': "All"
            }
        self.participant_page_offset = getattr(self, 'participant_page_offset', 0)
        while True:
            if not self.commands_queue:
                print_menu_header("participants")
                assistant_header_write(self, ["Participant Management Menu"])
            menu_options: MenuOptions = {}

            # Fetch participants from the API
            participants_ok, data = self.api("GET", "participants/get_participants")
            participants = data.get("participants", []) if participants_ok and data else []
            if participants and not self.commands_queue:
                sorted_filtered = _sort(_filter(participants))
                for p in sorted_filtered:
                    key = str(p['subid'])
                    if key in menu_options:
                        # subid isn't uniqueness-enforced anywhere in this
                        # codebase (unlike unique_id, which is -- see
                        # ParticipantManager's I4 invariant) -- fall back
                        # to unique_id for this entry rather than silently
                        # overwriting the earlier one's menu key and making
                        # it unreachable from this menu.
                        key = str(p['unique_id'])
                    menu_options[key] = {
                        'description': f"{p['subid']} ({p['initials']}, {p['unique_id']})",
                        'menu_caller': lambda self, participant_id = p['unique_id']: individual_participant_menu(self, participant_id)
                    }

                # Pagination -- requested directly, replacing the old
                # 3-column grid with a spreadsheet-style one-row-per-
                # participant table (like the underlying CSV). Every
                # participant above is still dispatchable directly by
                # sub ID regardless of which page is currently on screen
                # (menu_options is built from the FULL sorted_filtered
                # list, not just the current page) -- pagination only
                # affects what gets printed, never what's reachable.
                page_size = max(1, ui_state.window_height)
                total = len(sorted_filtered)
                max_offset = max(0, (total - 1) // page_size * page_size)
                self.participant_page_offset = max(0, min(self.participant_page_offset, max_offset))
                offset = self.participant_page_offset
                page = sorted_filtered[offset:offset + page_size]

                print("Enter a participant's sub ID to select them, or choose another option.")
                print("Current Display Mode:", red(self.participant_display_mode))
                print("Current Filter Settings:", self.participant_filter_settings)
                print_dashes()
                _print_participant_table(page)
                print_dashes()
                print(f"Showing {offset + 1}-{min(offset + page_size, total)} of {total} participants.")
                if offset + page_size < total:
                    menu_options['next'] = {'description': 'Show Next Page of Participants', 'menu_caller': next_participants_page_menu}
                if offset > 0:
                    menu_options['previous'] = {
                        'description': 'Show Previous Page of Participants', 'menu_caller': previous_participants_page_menu
                    }
            else:
                if not self.commands_queue:
                    print(f"{red('No participants found or failed to retrieve.')}")
                    print()
            menu_options['add'] = {'description': 'Add a Participant', 'menu_caller': add_participant_menu}
            menu_options['schedule'] = {'description': 'Get Participant Task Schedule', 'menu_caller': print_task_schedule}
            menu_options['refresh'] = {'description': 'Full Participants Refresh from CSV', 'menu_caller': refresh_participants_menu}
            menu_options['announcement'] = {'description': 'Send Study Announcement', 'menu_caller': send_announcement_menu}
            menu_options['send_ema'] = {'description': 'Send EMA to Everyone Now', 'menu_caller': send_studywide_ema_menu}
            menu_options['send_feedback'] = {
                'description': 'Send Feedback to Everyone Now', 'menu_caller': send_studywide_feedback_menu
            }
            menu_options['remove'] = {'description': 'Remove a Participant', 'menu_caller': remove_participant_menu}
            menu_options['sort'] = {'description': f'Sort Participants (Current: {self.participant_display_mode})', 'menu_caller': change_display_mode}
            menu_options['filter'] = {'description': 'Filter Participants', 'menu_caller': filter_participants_menu}

            # Study-wide ema_on/ema_off/feedback_on/feedback_off (requested
            # directly): both commands always shown, description reflects
            # current status so the RA can tell at a glance which one is
            # actionable without having to remember state across menu
            # redraws. Fails soft (assumes not-paused) if the status fetch
            # itself fails, rather than blocking the whole menu on it.
            pause_ok, pause_status = self.api("GET", "participants/get_survey_pause_status")
            ema_paused = bool(pause_ok and pause_status and pause_status.get('ema_paused'))
            feedback_paused = bool(pause_ok and pause_status and pause_status.get('feedback_paused'))
            menu_options['ema_on'] = {
                'description': f"Resume EMA Sends for Today (currently: {'PAUSED' if ema_paused else 'ON'})",
                'menu_caller': ema_on_menu,
            }
            menu_options['ema_off'] = {
                'description': f"Pause EMA Sends for Today (currently: {'PAUSED' if ema_paused else 'ON'})",
                'menu_caller': ema_off_menu,
            }
            menu_options['feedback_on'] = {
                'description': f"Resume Feedback Sends for Today (currently: {'PAUSED' if feedback_paused else 'ON'})",
                'menu_caller': feedback_on_menu,
            }
            menu_options['feedback_off'] = {
                'description': f"Pause Feedback Sends for Today (currently: {'PAUSED' if feedback_paused else 'ON'})",
                'menu_caller': feedback_off_menu,
            }
            
            if print_menu_options(self, menu_options, submenu = True):
                break
    except ReturnToMainMenu:
        # this menu wraps its whole dispatch loop in a try/except (unlike
        # most other menu files), so it needs its own explicit carve-out --
        # otherwise "home" typed from anywhere nested under participants/
        # (e.g. deep inside individual_participant_menu) would be caught
        # here and swallowed into an error() message instead of unwinding
        # to the main menu.
        raise
    except Exception as e:
        error(f"An error occurred in the participant management menu: {e}", self)

ADD_PARTICIPANT = add_participant_menu

PARTICIPANT_REFRESH = refresh_participants_menu

PARTICIPANT_ANNOUNCEMENT = send_announcement_menu