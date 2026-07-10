"""globals and global editing functions"""

# UIState/ui_state actually live in the tiny dependency-free _ui_state.py
# leaf module, not here -- see that module's docstring for why: _display.py/
# _menu_navigation.py/_menu_display.py (imported below, directly or
# transitively) each need `ui_state` at their own top of file, and importing
# it from *this* module would be a real circular import for whichever of
# them happens to be the first one Python loads. Re-exported here so
# `from user_interface_menus._menu_helper import ui_state` (used by files
# loaded well after this module has fully initialized) keeps working.
from user_interface_menus._ui_state import ui_state

from user_interface_menus.utils._display import *
from user_interface_menus.utils._menu_display import *
from user_interface_menus._types import Interface, MenuOptions

def set_window_width(width: int) -> None:
    if isinstance(width, int) and width > 0:
        ui_state.window_width = width
    else:
        error("Window width must be a positive integer.")
    save_params()

def set_window_height(height: int) -> None:
    if isinstance(height, int) and height > 0:
        ui_state.window_height = height
    else:
        error("Window height must be a positive integer.")
    save_params()

def toggle_right_align(self: Interface | None = None) -> None:
    ui_state.right_align = not ui_state.right_align
    save_params()

def set_show_readme(show: bool) -> None:
    ui_state.show_readme = show
    save_params()

def toggle_color_output(self: Interface) -> None:
    ui_state.color_on = not ui_state.color_on
    save_params()

def set_related_options_threshold(new_threshold: float) -> None:
    ui_state.related_options_threshold = new_threshold
    save_params()

def set_best_options_threshold(new_threshold: float) -> None:
    ui_state.best_options_threshold = new_threshold
    save_params()

def set_assistant_type_speed(speed: float) -> None:
    print(speed)
    if isinstance(speed, (int, float)) and speed > 0:
        ui_state.assistant_type_speed = speed
    else:
        error(f"Assistant type speed must be a positive number: {speed}")
    save_params()

def set_menu_delay(delay: float) -> None:
    if isinstance(delay, (int, float)) and delay >= 0:
        ui_state.menu_delay = delay
    else:
        error("Menu delay must be a non-negative number.")
    save_params()

def set_timeout(timeout: int) -> None:
    if isinstance(timeout, int) and timeout > 0:
        ui_state.timeout = timeout
    else:
        error("Timeout must be a positive integer.")
    save_params()

def add_recent_command(command: str) -> None:
    if command != 'recent' and command != 'command' and command not in ui_state.recent_commands:
        ui_state.recent_commands.append(command)
        if len(ui_state.recent_commands) > 10:
            ui_state.recent_commands.pop(0)

def set_local_menu_options(menu_name: str, menu_options: MenuOptions) -> None:
    ui_state.current_menu = menu_name
    ui_state.local_menu_options = menu_options

def print_local_menu_options(self: Interface | None = None) -> None:
    if ui_state.local_menu_options:
        print(f"\nLocal menu options ({yellow('/<command>')} to access):\n")
        for key, value in ui_state.local_menu_options.items():
            print(f"{yellow(key)}")
    print()

def get_local_menu_options() -> MenuOptions:
    return ui_state.local_menu_options

def load_params() -> None:
    import time

    clear()
    print("Now loading parameters...")
    file_path = ui_state.repo_root / "config" / "uiconfig.txt"
    with open(file_path, 'r') as file:
        lines = file.readlines()
        for line in lines:
            global_var = line.split("=")[0].strip()
            val = line.split("=")[1].strip()
            if global_var and val:
                if global_var == "RIGHT_ALIGN":
                    if val == "True":
                        ui_state.right_align = True
                        print(global_var, val)
                    elif val == "False":
                        ui_state.right_align = False
                        print(global_var, val)
                    else:
                        print(global_var, "INVALID, please update")
                elif global_var == "WINDOW_WIDTH":
                    try:
                        if int(val) and int(val) > 0 and int(val) < 200:
                            ui_state.window_width = int(val)
                            print(global_var, val)
                    except Exception as e:
                        print(global_var, "INVALID, please update")
                elif global_var == "WINDOW_HEIGHT":
                    try:
                        if int(val) and int(val) > 0 and int(val) < 100:
                            ui_state.window_height = int(val)
                            print(global_var, val)
                    except Exception as e:
                        print(global_var, "INVALID, please update")
                elif global_var == "RELATED_OPTIONS_THRESHOLD":
                    try:
                        if float(val) > 1.0 or float(val) < 0.0:
                            print(global_var, "INVALID, please update")
                        else:
                            ui_state.related_options_threshold = float(val)
                            print(global_var, val)
                    except Exception as e:
                        print(global_var, "INVALID, please update")
                elif global_var == "BEST_OPTIONS_THRESHOLD":
                    try:
                        if float(val) > 1.0 or float(val) < 0.0:
                            print(global_var, "INVALID, please update")
                        else:
                            ui_state.best_options_threshold = float(val)
                            print(global_var, val)
                    except Exception as e:
                        print(global_var, "INVALID, please update")
                elif global_var == "SHOW_README":
                    if val == "True":
                        ui_state.show_readme = True
                        print(global_var, val)
                    elif val == "False":
                        ui_state.show_readme = False
                        print(global_var, val)
                    else:
                        print(global_var, "INVALID, please update")
                elif global_var == "COLOR_ON":
                    if val == "True":
                        ui_state.color_on = True
                        print(global_var, val)
                    elif val == "False":
                        ui_state.color_on = False
                        print(global_var, val)
                    else:
                        print(global_var, "INVALID, please update")
                elif global_var == "MENU_DELAY":
                    try:
                        if float(val) < 0:
                            print(global_var, "INVALID, please update")
                        else:
                            ui_state.menu_delay = float(val)
                            print(global_var, val)
                    except Exception as e:
                        print(global_var, "INVALID, please update")
                elif global_var == "TIMEOUT":
                    try:
                        if int(val) <= 0:
                            print(global_var, "INVALID, please update")
                        else:
                            ui_state.timeout = int(val)
                            print(global_var, val)
                    except Exception as e:
                        print(global_var, "INVALID, please update")
                elif global_var == "ASSISTANT_TYPE_SPEED":
                    try:
                        if float(val) <= 0:
                            print(global_var, "INVALID, please update")
                        else:
                            ui_state.assistant_type_speed = float(val)
                            print(global_var, val)
                    except Exception as e:
                        print(global_var, "INVALID, please update")
    time.sleep(ui_state.menu_delay * 2)
    save_params()

def save_params() -> None:
    file_path = ui_state.repo_root / "config" / "uiconfig.txt"
    with open(file_path, 'w') as file:
        file.write(f"RIGHT_ALIGN={ui_state.right_align}\n")
        file.write(f"RELATED_OPTIONS_THRESHOLD={ui_state.related_options_threshold}\n")
        file.write(f"BEST_OPTIONS_THRESHOLD={ui_state.best_options_threshold}\n")
        file.write(f"ASSISTANT_TYPE_SPEED={ui_state.assistant_type_speed}\n")
        file.write(f"WINDOW_WIDTH={ui_state.window_width}\n")
        file.write(f"WINDOW_HEIGHT={ui_state.window_height}\n")
        file.write(f"SHOW_README={ui_state.show_readme}\n")
        file.write(f"COLOR_ON={ui_state.color_on}\n")
        file.write(f"MENU_DELAY={ui_state.menu_delay}\n")
        file.write(f"TIMEOUT={ui_state.timeout}\n")

def load_menus() -> None:
    clear()
    print("Now loading menus...")
    from user_interface_menus.utils._commands import init_commands
    ui_state.menu_options = init_commands()

def write_to_interface_log(message: str) -> None:
    try:
        import os
        log_dir = ui_state.repo_root / "logs" / "interface_logs"
        os.makedirs(log_dir, exist_ok=True)
        with open(log_dir / "test_interface_log.txt", "a") as file:
            file.write(f"{message}\n")
    except Exception as e:
        print(f"Error: Could not write to log file: {e}")

def read_from_interface_log() -> str:
    try:
        with open(ui_state.repo_root / "logs" / "interface_logs" / "test_interface_log.txt", "r") as file:
            content = file.read()
        return content
    except FileNotFoundError:
        print("Interface log file not found.")
        return ""
    except Exception as e:
        print(f"An unexpected error occurred while reading the interface log: {e}")
        return ""

# Startup README display: relocated from the now-removed help/_help_menu.py
# (2026-07-10 removal of the help-menu tree) because prism_interface.py
# imports README directly to show it on startup when SHOW_README is True --
# this is not part of the help-menu navigation tree being removed.

read_me_lines: list[str] = [
    f"I recommend looking through the commands available via {yellow('command')}.",
    f"\nYou can search for commands by typing {yellow('command <query>')} or {yellow('?<query>')}. Leave {yellow('<query>')} empty to search for all commands.",
    f"Most commands are globally accessible but some are only available in specific menus.",
    f"Commands are specified in {yellow('yellow')}.",
    f"Example: To toggle color mode, use the command {yellow('display color')}.",
    f"\nThere is also a command chaining feature that allows you to chain commands together using the {yellow('/')} character for commands and {yellow('?')} for user inputs.",
    f"Example, to schedule the second available R script at midnight, you can use the command chain {yellow('/tasks/add/rscript?2?00:00:00')}",
    f"\nTL;DR: You can navigate the entire user interface using what you see on the screen, but you can use commands to access features more quickly.",
    f"Command chaining is done with {yellow('/')}, but regular commands do not require this prefix.",
    f"\nTo stop this message from displaying on startup use the command {yellow('readme set')}."
]

def read_me(self: Interface) -> None:
    if not self.commands_queue:
        print_menu_header("readme")
        for line in read_me_lines:
            print(line)
        exit_menu()

README = read_me
