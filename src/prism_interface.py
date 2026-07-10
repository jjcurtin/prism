"""Main runner for the RA PRISM interface"""

from typing import Any

import requests, queue
from collections import deque

from user_interface_menus._main_menu import main_menu
from user_interface_menus._menu_helper import README, load_menus, exit_menu, load_params, ui_state

class PRISMInterface:
    # Attributes set outside __init__, dynamically, by the various menu
    # functions under user_interface_menus/ (which take `self` as a plain
    # first argument -- see user_interface_menus/_types.py). Declared here
    # (type only, no value) so those modules' `self: Interface` annotations
    # type-check against the real shape of this object.
    debug: bool
    participant_display_mode: str
    participant_filter_settings: dict[str, str]
    scheduled_tasks: list[dict[str, Any]]
    saved_positions: list[tuple[int | None, int | None]]
    column_width: int
    window_height: int
    num_columns: int

    def __init__(self) -> None:
        self.base_url = "http://localhost:5000/"
        ok, _ = self.api("GET", "system/uptime")
        if not ok:
            print("PRISM instance is not running or is not accessible. Please start the PRISM server first.")
            exit(0)

        self.inputs_queue: queue.Queue[str] = queue.Queue()
        self.commands_queue: deque[str] = deque()
        self.debug = False

        if ui_state.show_readme == True:
            README(self)
        main_menu(self)

    def api(self, method: str, endpoint: str, json: dict[str, Any] | None = None) -> tuple[bool, Any]:
        """Talks to the PRISM Flask server over HTTP. Returns a (ok, data)
        tuple rather than a bare value: `ok` is True only for a real HTTP 200
        response, `data` is the parsed JSON body in that case (None
        otherwise). This keeps a legitimately falsy-but-successful response
        (e.g. an empty list/dict) distinguishable from any of the several
        failure modes below (connection error, timeout, other exception, or
        a non-200 HTTP response) -- all of which previously collapsed to the
        same bare `None`, indistinguishable from each other and from a
        successful-but-empty body. Every caller must unpack the tuple; see
        each user_interface_menus/ menu function for the pattern
        (`ok, data = self.api(...)`).
        """
        try:
            url = f'{self.base_url}/{endpoint}'
            if method == "GET":
                r = requests.get(url, timeout = ui_state.timeout)
            elif method == "POST":
                r = requests.post(url, json = json, timeout = ui_state.timeout)
            elif method == "PUT":
                r = requests.put(url, timeout = ui_state.timeout)
            elif method == "DELETE":
                r = requests.delete(url, timeout = ui_state.timeout)
            else:
                raise ValueError("Invalid HTTP method")

            if r.status_code == 200:
                return True, r.json()
            print(f"PRISM server returned an error (status {r.status_code}).")
        except requests.ConnectionError:
            print("Connection error occurred while trying to reach the PRISM server.")
        except requests.Timeout:
            print("Request timed out. Please check the PRISM server or increase the timeout value.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        return False, None

    def get_task_types(self) -> dict[str, str]:
        ok, data = self.api("GET", "system/get_task_types")
        return data.get("task_types", {}) if ok and data else {}

    def request_transcript(self, lines: str | int, log_type: str) -> None:
        ok, data = self.api("GET", f"system/{log_type}/{lines}")
        if ok and data and "transcript" in data:
            for entry in data["transcript"]:
                print(f"{entry['timestamp']} - {entry['message']}")
        else:
            print("No transcript found or failed to retrieve.")

if __name__ == "__main__":
    try:
        load_params()
        load_menus()
        PRISMInterface()
    except KeyboardInterrupt:
        if ui_state.color_on:
            print("\033[32m\nExiting PRISM Interface.\033[0m")
        else:
            print("\nExiting PRISM Interface.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        exit_menu()