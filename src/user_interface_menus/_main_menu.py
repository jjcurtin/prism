# first menu shown on startup of the user interface

from user_interface_menus._menu_helper import *
from user_interface_menus.utils._menu_navigation import ReturnToMainMenu
from user_interface_menus.check._system_check_menu import system_check_menu
from user_interface_menus.tasks._system_task_menu import system_task_menu
from user_interface_menus.participants._participant_management_menus import participant_management_menu
from user_interface_menus.logs._log_menu import log_menu
from user_interface_menus._shutdown_menu import shutdown_menu
from user_interface_menus.settings._settings_menu import settings_menu

# ------------------------------------------------------------

def main_menu(self):
    menu_options = {
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
            menu_loop(self, menu_options, submenu = False, recommended_actions = ['participants', 'tasks'])
            break
        except ReturnToMainMenu:
            continue