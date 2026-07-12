"""system settings for the user interface"""

from user_interface_menus._menu_helper import *
# Already reachable via the `import *` above (ui_state has no leading
# underscore), but named explicitly here since this file reads several of
# its attributes directly in function bodies below.
from user_interface_menus._menu_helper import ui_state
from user_interface_menus._types import Interface, MenuOptions

def window_width_settings(self: Interface) -> int | None:
    print("Current PRISM window width:", ui_state.window_width)
    new_width = get_input(self, prompt = "Enter new width between 80 and 200: ")
    if not new_width.isdigit():
        error("Window width must be an integer.")
        return 0
    if int(new_width) > 200 or int(new_width) < 80:
        error("Window width cannot exceed 200 characters.")
        return 0
    set_window_width(int(new_width))
    return None

def window_height_settings(self: Interface) -> int | None:
    print("Current PRISM window height:", ui_state.window_height)
    new_height = get_input(self, prompt = "Enter new height between 5 and 15: ")
    if not new_height.isdigit():
        error("Window height must be an integer.")
        return 0
    if int(new_height) < 5 or int(new_height) > 15:
        error("Window height must be between 5 and 15 lines.")
        return 0
    set_window_height(int(new_height))
    return None

def print_display_params(self: Interface) -> None:
    if not self.commands_queue:
        print()
        print(f"PRISM window width: {ui_state.window_width}")
        print(f"Right alignment of menu options: {'enabled' if ui_state.right_align else 'disabled'}")
        print(f"Color output in terminal: {'enabled' if ui_state.color_on else 'disabled'}")
        exit_menu()

def display_settings(self: Interface) -> None:
    menu_options: MenuOptions = {
        'print': {'description': 'Print current system parameters', 'menu_caller': print_display_params},
        'width': {'description': 'Adjust PRISM window width', 'menu_caller': window_width_settings},
        'height': {'description': 'Adjust PRISM window height', 'menu_caller': window_height_settings},
        'align': {'description': 'Toggle right alignment of menu options', 'menu_caller': toggle_right_align},
        'color': {'description': 'Toggle color output in terminal', 'menu_caller': toggle_color_output},
    }

    while True:
        if not self.commands_queue:
            print_menu_header("settings display")
            assistant_header_write(self, ["Display Settings Menu"])
        if print_menu_options(self, menu_options, submenu = True):
            break

def related_parameter(self: Interface) -> int | None:
    print("Current threshold:", ui_state.related_options_threshold)
    new_threshold = get_input(self, prompt = "Enter new threshold (ranges 0.0 to 1.0): ")
    if new_threshold == '':
        return 0
    try:
        if float(new_threshold) > 1.0 or float(new_threshold) < 0.0:
            error("Threshold must be within the range 0.0 to 1.0.")
            return 0
    except Exception as e:
        error("Invalid input. Please try again.")
        return 0
    set_related_options_threshold(float(new_threshold))
    return None


def best_related_parameter(self: Interface) -> int | None:
    print("Current threshold:", ui_state.best_options_threshold)
    new_threshold = get_input(self, prompt = "Enter new threshold (ranges 0.0 to 1.0): ")
    if new_threshold == '':
        return 0
    try:
        if float(new_threshold) > 1.0 or float(new_threshold) < 0.0:
            error("Threshold must be within the range 0.0 to 1.0.")
            return 0
    except Exception as e:
        error("Invalid input. Please try again.")
        return 0
    set_best_options_threshold(float(new_threshold))
    return None

def menu_delay_parameter(self: Interface) -> int | None:
    print("Current menu delay:", ui_state.menu_delay)
    new_delay = get_input(self, prompt = "Enter new menu delay (must be a positive number): ")
    if new_delay == '':
        return 0
    try:
        if float(new_delay) <= 0:
            error("Menu delay must be a positive number.")
            return 0
    except Exception as e:
        error("Invalid input. Please try again.")
        return 0
    set_menu_delay(float(new_delay))
    return None

def timeout_parameter(self: Interface) -> int | None:
    print("Current timeout:", ui_state.timeout)
    new_timeout = get_input(self, prompt = "Enter new timeout (must be a positive integer): ")
    if new_timeout == '':
        return 0
    try:
        if int(new_timeout) <= 0:
            error("Timeout must be a positive integer.")
            return 0
    except Exception as e:
        error("Invalid input. Please try again.")
        return 0
    set_timeout(int(new_timeout))
    return None

def param_set_type_speed(self: Interface) -> int | None:
    print("Current header type speed:", ui_state.assistant_type_speed)
    new_speed = get_input(self, prompt = "Enter new type speed (must be a positive number recommended 0.015): ")
    print(f"New type speed: {new_speed}")
    if new_speed == '':
        return 0
    try:
        if float(new_speed) < 0.001 or float(new_speed) > 0.03:
            error(f"Type speed must be a positive number between 0.001 and 0.03: {new_speed}")
            return 0
    except Exception as e:
        error("Invalid input. Please try again.")
        return 0
    set_assistant_type_speed(float(new_speed))
    return None

def print_params(self: Interface) -> None:
    if not self.commands_queue:
        print(f"RELATED_OPTIONS_THRESHOLD: {ui_state.related_options_threshold}")
        print(f"BEST_OPTIONS_THRESHOLD: {ui_state.best_options_threshold}")
        print(f"ASSISTANT_TYPE_SPEED: {ui_state.assistant_type_speed}")
        print(f"MENU_DELAY: {ui_state.menu_delay}")
        print(f"TIMEOUT: {ui_state.timeout}")
        exit_menu()

def parameter_settings(self: Interface) -> None:
    menu_options: MenuOptions = {
        'print': {'description': 'Print current system parameters', 'menu_caller': print_params},
        'threshold': {'description': 'Adjust the minimum command prediction similarity tolerance', 'menu_caller': related_parameter},
        'best threshold': {'description': 'Adjust the prioritized "best" command prediction similarity tolerance', 'menu_caller': best_related_parameter},
        'type speed': {'description': 'Adjust the typing speed of header messages', 'menu_caller': param_set_type_speed},
        'delay': {'description': 'Adjust the delay between menu displays', 'menu_caller': menu_delay_parameter},
        'timeout': {'description': 'Adjust the user interface timeout for API calls', 'menu_caller': timeout_parameter},
    }

    while True:
        if not self.commands_queue:
            print_menu_header("settings system params")
        if print_menu_options(self, menu_options, submenu = True):
            break

def readme(self: Interface) -> None:
    if ui_state.show_readme:
        print("PRISM Readme is currently enabled.")
    else:
        print("PRISM Readme is currently disabled.")
    
    show_on_startup = prompt_confirmation(self, prompt = "Show README on startup?")
    set_show_readme(show_on_startup)
    success(f"PRISM Readme on startup {'enabled' if show_on_startup else 'disabled'}.", self)

def system_settings(self: Interface) -> None:
    menu_options: MenuOptions = {
        'params': {'description': 'Adjust system parameters', 'menu_caller': parameter_settings},
        'readme set': {'description': 'Toggle display of the PRISM Readme on startup', 'menu_caller': readme},
    }

    while True:
        if not self.commands_queue:
            print_menu_header("settings system")
            assistant_header_write(self, ["System Settings Menu"])
        if print_menu_options(self, menu_options, submenu = True):
            break

def settings_menu(self: Interface) -> None:
    menu_options: MenuOptions = {
        'system': {'description': 'System Settings', 'menu_caller': system_settings},
        'display': {'description': 'Manage Display settings', 'menu_caller': display_settings}
    }

    while True:
        if not self.commands_queue:
            print_menu_header("settings")
            assistant_header_write(self, ["Settings Menu"])
        if print_menu_options(self, menu_options, submenu = True):
            break

DISPLAY = display_settings

READ_ME_SET = readme

WINDOW_WIDTH_SETTINGS = window_width_settings

PARAM_WINDOW_HEIGHT = window_height_settings

SYSTEM_SETTINGS = system_settings

PARAMETER_SETTINGS = parameter_settings

PRINT_PARAMS = print_params

PARAM_MENU_DELAY = menu_delay_parameter

PARAM_TIMEOUT = timeout_parameter

PARAM_RELATED_THRESHOLD = related_parameter

PARAM_BEST_OPTIONS_THRESHOLD = best_related_parameter

PARAM_ASSISTANT_TYPE_SPEED = param_set_type_speed