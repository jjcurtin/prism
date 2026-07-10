# Main runner for the RA PRISM interface

import requests, queue
from collections import deque

from user_interface_menus._main_menu import main_menu
from user_interface_menus._menu_helper import README, load_menus, exit_menu, load_params

class PRISMInterface:
    def __init__(self):
        self.base_url = "http://localhost:5000/"
        ok, _ = self.api("GET", "system/uptime")
        if not ok:
            print("PRISM instance is not running or is not accessible. Please start the PRISM server first.")
            exit(0)

        self.inputs_queue = queue.Queue()
        self.commands_queue = deque()
        self.debug = False

        from user_interface_menus._menu_helper import SHOW_README
        if SHOW_README == True:
            README(self)
        main_menu(self)

    def api(self, method, endpoint, json=None):
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
        from user_interface_menus._menu_helper import TIMEOUT
        try:
            url = f'{self.base_url}/{endpoint}'
            if method == "GET":
                r = requests.get(url, timeout = TIMEOUT)
            elif method == "POST":
                r = requests.post(url, json = json, timeout = TIMEOUT)
            elif method == "PUT":
                r = requests.put(url, timeout = TIMEOUT)
            elif method == "DELETE":
                r = requests.delete(url, timeout = TIMEOUT)
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

    def get_task_types(self):
        ok, data = self.api("GET", "system/get_task_types")
        return data.get("task_types", {}) if ok and data else {}

    def request_transcript(self, lines, log_type):
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
        from user_interface_menus._menu_helper import COLOR_ON
        if COLOR_ON:
            print("\033[32m\nExiting PRISM Interface.\033[0m")
        else:
            print("\nExiting PRISM Interface.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        exit_menu()