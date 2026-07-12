"""first menu shown on startup of the user interface"""

import re

from user_interface_menus._menu_helper import *
from user_interface_menus.utils._menu_navigation import ReturnToMainMenu
from user_interface_menus.check._system_check_menu import system_check_menu
from user_interface_menus.tasks._system_task_menu import system_task_menu
from user_interface_menus.participants._participant_management_menus import participant_management_menu
from user_interface_menus.logs._log_menu import log_menu
from user_interface_menus._shutdown_menu import shutdown_menu
from user_interface_menus.settings._settings_menu import settings_menu
from user_interface_menus._types import Interface, MenuOptions

# Matches every system task's own completion line (SystemTask.execute(),
# src/system_tasks/_system_task.py): "{LEVEL} - {task_type} #{task_number}
# completed with status: {SUCCESS|FAILURE}." -- every real task subclass
# (CheckSystem, RunRScript) logs exactly this line, success or failure, so
# it's a reliable, single-format target to scan the transcript for, rather
# than trying to track "recent tasks" as new state.
RECENT_SYSTEM_TASK_RE = re.compile(
    r'^(?:\w+ - )?(?P<task_type>\S+) #(?P<task_number>\d+) completed with status: (?P<status>SUCCESS|FAILURE)\.$'
)
RECENT_SYSTEM_TASKS_LIMIT = 5
RECENT_SYSTEM_TASKS_SCAN_LINES = 200

def _recent_system_task_lines(self: Interface) -> list[str]:
    ok, data = self.api("GET", f"system/get_transcript/{RECENT_SYSTEM_TASKS_SCAN_LINES}")
    if not ok or not data or "transcript" not in data:
        return [f"  {red('Unable to retrieve recent system tasks.')}"]
    matches: list[tuple[str, str, str, str]] = []
    for entry in data["transcript"]:
        match = RECENT_SYSTEM_TASK_RE.match(entry.get("message", ""))
        if match:
            matches.append((
                entry.get("timestamp", ""), match["task_type"], match["task_number"], match["status"],
            ))
    matches = matches[-RECENT_SYSTEM_TASKS_LIMIT:]
    if not matches:
        return [f"  {red('No recent system tasks found.')}"]
    return [
        f"  {timestamp}  {task_type} #{task_number} - {green(status) if status == 'SUCCESS' else red(status)}"
        for timestamp, task_type, task_number, status in matches
    ]

def _send_count_lines(self: Interface) -> list[str]:
    ok, counts = self.api("GET", "participants/get_send_counts")
    if not ok or not counts:
        return [f"  {red('Unable to retrieve send counts.')}"]
    return [
        f"  EMA sent today - on study: {counts['ema_on_study_sent']}/{counts['ema_on_study_total']}"
        f"   all participants: {counts['ema_all_sent']}/{counts['ema_all_total']}",
        f"  Feedback sent today - on study: {counts['feedback_on_study_sent']}/{counts['feedback_on_study_total']}"
        f"   all participants: {counts['feedback_all_sent']}/{counts['feedback_all_total']}",
    ]

def _start_time_line(self: Interface) -> str:
    ok, data = self.api("GET", "system/start_time")
    start_time = data.get("start_time") if ok and data else None
    return f"  PRISM started: {start_time if start_time else red('unavailable')}"

def build_main_menu_status_panel(self: Interface) -> list[str]:
    """additional_content callback for menu_loop -- requested directly: a
    status window above the main menu's command area showing recent system
    task activity, today's EMA/feedback send counts, and when PRISM
    started. Re-fetched on every redraw (menu_loop calls this fresh each
    time), same live-refresh convention as the check menu's uptime/mode.
    """
    return [
        f"{yellow('Recent System Tasks')}",
        *_recent_system_task_lines(self),
        "-",
        _start_time_line(self),
        *_send_count_lines(self),
        "-",
    ]

def main_menu(self: Interface) -> None:
    menu_options: MenuOptions = {
        'command': {'description': 'Global Command Menu', 'menu_caller': print_global_command_menu},
        'check': {'description': 'System Status and Diagnostics', 'menu_caller': system_check_menu},
        'tasks': {'description': 'Manage System Tasks/R Scripts', 'menu_caller': system_task_menu},
        'participants': {'description': 'Manage Participants', 'menu_caller': participant_management_menu},
        'logs': {'description': 'View Logs', 'menu_caller': log_menu},
        'settings': {'description': 'Settings', 'menu_caller': settings_menu},
        'shutdown': {'description': 'Shutdown PRISM', 'menu_caller': shutdown_menu},
        'exit': {'description': 'Exit PRISM User Interface', 'menu_caller': exit_interface}
    }

    # The "home" global command (_menu_display.py's check_for_special_commands)
    # raises ReturnToMainMenu from however deep in the nested submenu call
    # stack it's issued from; every blanket except-Exception on the
    # navigation path between there and here re-raises it instead of
    # swallowing it (see ReturnToMainMenu's docstring in
    # utils/_menu_navigation.py for the full list of carve-outs). This is
    # the true top level where it's actually caught: loop back and redraw a
    # fresh main menu instead of propagating further (which would otherwise
    # crash the interface) or being reported as an error.
    while True:
        try:
            menu_loop(self, menu_options, submenu = False, additional_content = build_main_menu_status_panel)
            break
        except ReturnToMainMenu:
            continue