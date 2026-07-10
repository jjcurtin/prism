"""menu for adding a participant"""

import random
import time

from user_interface_menus.utils._menu_display import *
from user_interface_menus._menu_helper import *
from user_interface_menus._types import Interface

def add_participant_menu(self: Interface) -> None:
    """Generates a random 9-digit unique_id when the user doesn't supply a
    valid one, and regenerates again if that ID collides with an existing
    participant -- the ID actually saved may not be what the user typed (or
    the first one generated).
    """
    if not self.commands_queue:
        print_menu_header("participants add")
    initials = get_input(self, prompt = "Initials: ")
    if not initials:
        error("Initials are required.", self)
        return
    subid = get_input(self, prompt = "Sub ID: ")
    if not subid or not subid.isnumeric():
        error("Sub ID is required and must be a number.", self)
        return
    unique_id = get_input(self, prompt = "Unique ID: ")
    if not unique_id or not unique_id.isnumeric() or len(unique_id) != 9:
        unique_id = str(random.randint(100000000, 999999999))
        print(f"Unique ID not valid. Generated: {unique_id}")
    existing_ok, existing_participants = self.api("GET", "participants/get_participants")
    if existing_ok and existing_participants:
        for participant in existing_participants.get("participants", []):
            if participant.get("unique_id") == unique_id:
                new_unique_id = str(random.randint(100000000, 999999999))
                print(f"Unique ID '{unique_id}' already exists. Generated a new one: {new_unique_id}")
                unique_id = new_unique_id
    on_study = prompt_confirmation(self, prompt = "On study?")
    phone_number = get_input(self, prompt = "Phone number (press enter to skip): ")
    times = {}
    default_times = {
        'ema_time': '16:00:00',
        'ema_reminder_time': '19:00:00',
        'feedback_time': '07:00:00',
        'feedback_reminder_time': '12:00:00'
    }
    for t in ['ema_time', 'ema_reminder_time', 'feedback_time', 'feedback_reminder_time']:
        val = get_input(self, prompt = f"Enter {t.replace('_', ' ')} (HH:MM:SS) ", default_value = default_times[t]) or default_times[t]
        try:
            time.strptime(val, '%H:%M:%S')
            times[t] = val
        except ValueError:
            print(f"Invalid time format for {val}. Using default: {default_times[t]}.\nYou can change this later.")
            times[t] = default_times[t]
    payload = dict(initials = initials,
                    subid = subid,
                    unique_id = unique_id,
                    on_study = on_study,
                    phone_number = phone_number,
                    **times)
    ok, _ = self.api("POST", "participants/add_participant", json = payload)
    if ok:
        success("Participant added.", self)
    else:
        error("Failed to add participant.", self)