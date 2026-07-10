"""display api"""

from typing import Any, Callable

import os, sys, time
from user_interface_menus.utils._keyboard import kbhit, getwch, read_arrow_key, raw_mode
# `ui_state` is imported here (before any of this module's functions are
# defined) rather than inside each function body, unlike WINDOW_WIDTH/
# COLOR_ON/etc. previously -- those were re-imported fresh on every call
# because the bare names went stale the moment a setter in _menu_helper.py
# reassigned them. `ui_state` itself is never reassigned (only its
# attributes are mutated in place), so this single reference stays live.
# Imported from _ui_state.py (a leaf module with no further internal
# imports), not from _menu_helper.py itself -- _menu_helper.py imports this
# module (_display) via `from user_interface_menus.utils._display import *`
# at its own top, so importing `ui_state` back from _menu_helper here would
# be a real circular import whenever _display.py (or _menu_navigation.py/
# _menu_display.py, which import it too) happens to be the first module
# Python loads. See _ui_state.py's docstring for the full explanation.
from user_interface_menus._ui_state import ui_state
from user_interface_menus._types import Interface

def clear() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')

def toggle_debug_mode(self: Interface) -> None:
    self.debug = not self.debug

def green(message: object = None) -> str:
    green, color_end = ("\033[32m", "\033[0m") if ui_state.color_on else ("\033[1m", "\033[0m")
    return f"{green}{message}{color_end}"

def red(message: object = None) -> str:
    red, color_end = ("\033[31m", "\033[0m") if ui_state.color_on else ("\033[1m", "\033[0m")
    return f"{red}{message}{color_end}"

def yellow(message: object = None) -> str:
    yellow, color_end = ("\033[33m", "\033[0m") if ui_state.color_on else ("\033[4m", "\033[0m")
    return f"{yellow}{message}{color_end}"

def cyan(message: object = None) -> str:
    cyan, color_end = ("\033[36m", "\033[0m") if ui_state.color_on else ("", "")
    return f"{cyan}{message}{color_end}"

def white(message: object = None) -> str:
    white, color_end = ("\033[37m", "\033[0m") if ui_state.color_on else ("", "")
    return f"{white}{message}{color_end}"

# A "syntax item" pairs a color function (green/red/yellow/cyan/white above)
# with the substring it should be applied to -- see syntax_highlight() and
# syntax_highlight_string() below, and their callers (e.g.
# print_fixed_terminal_prompt()'s scan_recovered_string()).
SyntaxItem = tuple[Callable[[object], str], str]

def syntax_highlight(self: Interface, prompt: str = "", items: list[SyntaxItem] | None = None) -> None:
    if not ui_state.color_on:
        return
    curr_pos = get_cursor_position()
    # curr_pos[1] can be None (a failed ANSI cursor-position read -- see
    # get_cursor_position()'s own return type below); fall back to 0, the
    # same convention display_in_columns()'s assemble_content() uses for a
    # failed read.
    curr_y = curr_pos[1] if curr_pos[1] is not None else 0
    move_cursor(self, 0, curr_y - 1)
    output = prompt
    for item in items:  # type: ignore[union-attr]
        output += item[0](item[1])
    print(output)

def syntax_highlight_string(
    self: Interface,
    input_string: str,
    prompt: str = "",
    items: list[SyntaxItem] | None = None,
    in_place: bool = False,
) -> None:
    try:
        if not ui_state.color_on or items is None:
            return
        curr_pos = get_cursor_position()
        if not in_place:
            # curr_pos[1] can be None (a failed ANSI cursor-position read);
            # same fallback-to-0 convention as syntax_highlight() above.
            curr_y = curr_pos[1] if curr_pos[1] is not None else 0
            move_cursor(self, 0, curr_y - 1)
        elif in_place:
            try:
                ansi_clear_line()
                # move_cursor() always returns None, so a `while
                # move_cursor(...): pass` loop here never runs its body --
                # it has only ever amounted to a single unconditional call
                # (confirmed back to this function's first version in
                # c5150da; move_cursor() has never returned a truthy value).
                # Simplified to what actually executes, no new looping
                # behavior introduced.
                move_cursor(self, 0, curr_pos[1])
            except Exception as e:
                error(f"ANSI error: " + str(e), self)
        
        output = input_string
        if items is not None:
            for item in items:
                if item[1] in input_string:
                    output = output.replace(item[1], item[0](item[1]))
        try:
            ansi_write_str(prompt + output)
        except Exception as e:
            print(f"Error writing to terminal: {e}")
    except Exception as e:
        print(f"Error in syntax_highlight_string: {e}")
        if self.debug:
            print(f"Input string: {input_string}, Prompt: {prompt}, Items: {items}")
        return

def align(
    self: Interface,
    text: str,
    column_number: int,
    num_columns: int,
    formatless: str | None = None,
    window_width: int | None = None,
    align_right: bool | None = None,
    locked: bool = False,
    border_left: bool = False,
    border_right: bool = False,
) -> str:
    import re

    if window_width is None:
        window_width = int(ui_state.window_width)
    if formatless is None:
        formatless = text
    if align_right is None:
        align_right = ui_state.right_align

    num_invisible_escape_chars = len(re.findall(r'\x1B\[[0-?]*[ -/]*[@-~]', text))
    compensation = (len(text) - len(formatless))
    format_width = int(window_width + compensation)

    if self.debug:
        print(f"size of window: {window_width}, text size = {len(text)}, formatless size = {len(formatless)}, escape chars = {compensation}")

    middle_screen_adjustment = (ui_state.window_width % num_columns)
    middle_screen_adjustment1 = middle_screen_adjustment // 2 + (middle_screen_adjustment % 2)
    middle_screen_adjustment2 = middle_screen_adjustment // 2

    if self.debug:
        print(f"\nmiddle screen adjustment: {green(middle_screen_adjustment)}\n")

    format_width += middle_screen_adjustment if (
        (column_number == 0 and num_columns == 2) or
        (column_number == 1 and num_columns == 3)
    ) else middle_screen_adjustment1 if (
        column_number == 1 and num_columns == 4
    ) else middle_screen_adjustment2 if (
        column_number == 2 and num_columns == 4
    ) else 0

    if locked:
        alignment = "<" if not align_right else ">"
    else:
        if align_right and not ui_state.right_align:
            alignment = "<"
        elif not align_right and ui_state.right_align:
            alignment = ">"
        else:
            alignment = ">" if align_right else "<"

    left, right = "", ""
    if border_left:
        left = "| "
    if border_right:
        right = " |"

    truncated = text[:(format_width)].rstrip()

    if self.debug:
        print(red(num_invisible_escape_chars), "invisible escape chars in text:", text)
        string = "\n"
        for i in range(0, len(truncated)):
            string += truncated[i] + " "
        length = int(len(string) / 2)
        color = green if length <= format_width else red
        print((color(string) + f" ({color(length)}" + " chars)"))

    output = ""

    if alignment == "<":
        final_string = f"{left}{truncated}"
        if border_right:
            format_width -= len(right)
        if self.debug:
            print(f"Truncated with left: {final_string}, alignment: {alignment}, format width: {format_width}\n")
        output = f"{final_string:{alignment}{format_width}}"
        output += right
    elif alignment == ">":
        final_string = f"{truncated}{right}"
        if border_left:
            format_width -= len(left)
        if self.debug:
            print(f"Truncated with right: {final_string}, alignment: {alignment}, format width: {format_width}\n")
        output = f"{final_string:{alignment}{format_width}}"
        output = left + output

    if self.debug:
        print("Final output:     " + repr(output))
        print(f"                  {red("-") * len(repr(output))}")
        print("Formatted input:  " + repr(text))
        print(f"                  {yellow("-") * len(repr(text))}")
        print("Formatless input: " + repr(formatless))
        print(f"                  {green('-') * len(repr(formatless))}")
        amount = len(output) - format_width - 2
        print(f"{yellow(format_width)} -> column {column_number + 1} of {num_columns}, output is {f"{red(amount)}" if amount != 0 else 0} chars over format width {format_width}\n")

    return output

DisplayItem = dict[str, Any]
# window_positions is a list of (x, y) screen coordinates, one per column.
WindowPositions = list[tuple[int, int]]

def display_in_columns(self: Interface, items: list[DisplayItem] | None = None) -> str | tuple[WindowPositions, int]:
    try:
        import re

        if self.debug:
            print(f"\n{items}\n")

        if items is None:
            return "Error: No items to display."
        num_segments = len(items)

        window_positions: WindowPositions = []

        def assemble_content() -> tuple[str, int]:
            column_width = int(ui_state.window_width / num_segments)
            frame_width = column_width
            output = ""
            initial_pos = get_cursor_position()
            initial_y = initial_pos[1] if initial_pos[1] is not None else 0

            line_text = ""
            if self.debug:
                print()
            for i, item in enumerate(items):

                if i % len(items) == 0:
                    line_text = ""

                ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
                item_formatless = ansi_escape.sub('', item['text'])
                border_settings = item.get('bordered', 'none')
                border_left = False
                border_right = False
                if border_settings == 'left' or border_settings == 'both':
                    border_left = True
                if border_settings == 'right' or border_settings == 'both':
                    border_right = True
                initial_x = len(output)
                if border_left:
                    initial_x += 2
                    frame_width = column_width - 2
                if self.debug:
                    print(f"Column {i + 1} of {num_segments}, initial x: {initial_x}, initial y: {initial_y}, column width: {column_width}, frame width: {frame_width}")
                window_positions.append((initial_x, initial_y))
                column_text = align(self,
                    item['text'], i, 
                    num_segments, formatless = item_formatless, 
                    window_width = column_width, 
                    align_right = item.get('align_right', False),
                    locked = item.get('locked', False),
                    border_left = border_left,
                    border_right = border_right,
                )
                line_text += column_text
                output += column_text

                if i % len(items) == 1:
                    pass
                    #print(line_text)
            return output, frame_width
        
        output, column_width = assemble_content()
        print(output)
        if self.debug:
            print(f"\nWindow positions: {window_positions}")
            print(f"Column width: {column_width}")
            print(f"\nEnter {yellow("debug")} to exit debug mode.")
        return window_positions, column_width
    except Exception as e:
        error(f"Error displaying items in columns: {e}", self)
        return [], 0

def error(message: str = "An unexpected error occurred.", self: Interface | None = None) -> None:
    from user_interface_menus.utils._menu_navigation import clear_commands_queue
    from user_interface_menus._menu_helper import write_to_interface_log

    print(f"{red('Error')}: {message}")
    try:
        write_to_interface_log(f"Error: {message}")
    except Exception as e:
        print(f"Error: Could not write to log file: {e}")

    # stop processing commands, error
    if self is not None:
        clear_commands_queue(self)
    exit_menu()

def success(message: str = "Operation completed successfully.", self: Interface | None = None) -> None:
    print(f"{green('Success')}: {message}")
    from user_interface_menus._menu_helper import write_to_interface_log
    try:
        write_to_interface_log(f"Success: {message}")
    except Exception as e:
        error(f"Could not write to log file: {e}")

    # skip exit menu
    if self is None or not self.commands_queue:
        exit_menu()

def exit_menu() -> None:
    input(f"\n{yellow("ENTER to Continue>")} ")

def exit_interface(self: Interface) -> None:
    print(green("Exiting PRISM Interface."))
    exit(0)

def print_menu_header(title: str) -> None:
    clear()
    padding = (ui_state.window_width - len(title)) // 2
    print_equals()
    print(" " * padding + f"{red(title)}")
    print_equals()

    print()
    print_dashes()
    print()

def print_dashes(delay: float | None = None) -> None:
    if delay is not None:
        for i in range(ui_state.window_width):
            print("-", end="", flush = True)
            time.sleep(delay)
    else:
        print("-" * ui_state.window_width)

def print_guide_lines(divisions: int, line_type: str, num_segments: int) -> None:
    max_divisions = 3
    if divisions > max_divisions:
        error(f"Maximum divisions is {max_divisions}. You requested {divisions}.")

    elif line_type == "dashes":
        chars = ['-', '-', '-', '-']
        if ui_state.color_on:
            chars = [f"\033[1;3{(i % 6) + 1}m{'-'}\033[0m" for i, char in enumerate(chars)]
        segment_length = ui_state.window_width // num_segments
        middle_screen_adjustment = (ui_state.window_width % num_segments)
        middle_screen_adjustment1 = middle_screen_adjustment // 2 + (middle_screen_adjustment % 2)
        middle_screen_adjustment2 = middle_screen_adjustment // 2
        s = "".join(
            "|" + (chars[i % len(chars)] * (
            segment_length - 2 + (
                middle_screen_adjustment if (
                (i == 0 and num_segments == 2) or
                (i == 1 and num_segments == 3)
                ) else middle_screen_adjustment1 if (
                    i == 1 and num_segments == 4
                ) else middle_screen_adjustment2 if (
                    i == 2 and num_segments == 4
                ) else 0
            )
            )) + "|"
            for i in range(num_segments)
        )
        print(s.strip())
    
    elif line_type == "dots":
        chars = ['|', '|', '|', '|']
        if ui_state.color_on:
            chars = [f"\033[1;3{(i % 6) + 1}m{'|'}\033[0m" for i, char in enumerate(chars)]
        segment_length = ui_state.window_width // num_segments
        middle_screen_adjustment = (ui_state.window_width % num_segments)
        middle_screen_adjustment1 = middle_screen_adjustment // 2 + (middle_screen_adjustment % 2)
        middle_screen_adjustment2 = middle_screen_adjustment // 2
        s = "".join(
            chars[i % len(chars)] + (" " * (
            segment_length - 2 + (
                middle_screen_adjustment if (
                (i == 0 and num_segments == 2) or
                (i == 1 and num_segments == 3)
                ) else middle_screen_adjustment1 if (
                    i == 1 and num_segments == 4
                ) else middle_screen_adjustment2 if (
                    i == 2 and num_segments == 4
                ) else 0
            ))) + chars[i % len(chars)]
            for i in range(num_segments)
        )
        print(s.strip())

def print_equals() -> None:
    print("=" * ui_state.window_width)

def print_fixed_terminal_prompt(self: Interface | None = None, submenu: bool = True) -> str:
    def scan_recovered_string(recovered_string: str) -> list[SyntaxItem]:
        from user_interface_menus.utils._menu_navigation import get_relevant_menu_options
        from user_interface_menus._menu_helper import get_local_menu_options
        import re
        items: list[SyntaxItem] = []
        if not recovered_string or not recovered_string.startswith('/'):

            if recovered_string.startswith("?"):
                items.append((yellow, recovered_string))
            else:
                if recovered_string.split("?"):
                    items.append((red, "?" + "".join(recovered_string.split("?")[1:])))
                if recovered_string.split("*"):
                    items.append((red, "*" + "".join(recovered_string.split("*")[1:])))
                if recovered_string.split("/"):
                    items.append((red, "/" + "".join(recovered_string.split("/")[1:])))
            return items

        # parse iterations
        if '*' in recovered_string:
            command_string, iterations = recovered_string.split('*', 1)
        else:
            command_string, iterations = recovered_string, None
        if iterations is not None:
            number = re.search(r'\d+', iterations)
            if number and number.group(0).isdigit():
                remaining = iterations[len(number.group(0)):]
                if remaining:
                    items.append((red, "*" + number.group(0) + remaining))
                else:
                    items.append((cyan, "*" + number.group(0)))
            else:
                items.append((red, "*" + iterations))
        
        # parse commands
        command_strings = command_string.split('/')
        for command in command_strings:
            if '?' in command:
                parts = command.split('?')
                cmd = parts[0]
                parameters = parts[1:] if len(parts) > 1 else []
            else:
                cmd, parameters = command, []
            cmd = cmd.strip()
            relevant_options = get_relevant_menu_options(cmd, exact_match = True)
            if cmd in relevant_options and len(relevant_options) == 1:
                items.append((yellow, "/" + cmd))
            local_options = get_local_menu_options()
            if cmd in local_options:
                items.append((yellow, "/" + cmd))

            # parse parameters
            for parameter in parameters:
                if parameter.strip():
                    items.append((green, '?' + parameter.strip()))
        return items

    prompt = cyan('\nprism> ')
    recovered_string = ""
    print()
    if self is not None:
        prompt = cyan('prism> ')
        print(prompt, end='', flush=True)
        recent_pointer = -1
        with raw_mode():
            while True:
                if not kbhit():
                    time.sleep(0.01)  # avoid busy-waiting the CPU while idle
                    continue
                key = getwch()

                arrow = read_arrow_key(key)
                if arrow == 'UP':
                    if ui_state.recent_commands:
                        recovered_string = ui_state.recent_commands[recent_pointer] if recent_pointer >= -len(ui_state.recent_commands) else ""
                        recent_pointer -= 1
                        if recent_pointer < -len(ui_state.recent_commands):
                            recent_pointer = -1
                elif arrow == 'DOWN':
                    if ui_state.recent_commands:
                        if recent_pointer < -1:
                            recent_pointer += 1
                        recovered_string = ui_state.recent_commands[recent_pointer] if recent_pointer >= -len(ui_state.recent_commands) else ""
                    else:
                        recent_pointer = -1
                elif arrow == 'LEFT':
                    # print("Left Arrow Pressed")
                    pass
                elif arrow == 'RIGHT':
                    # print("Right Arrow Pressed")
                    pass
                elif arrow is not None:
                    continue
                elif key == '\r' or key == '\n':
                    if len(recovered_string) == 0 and not submenu:
                        continue
                    break
                elif key in ('\b', '\x7f') and len(recovered_string) > 0:
                    recovered_string = recovered_string[:-1]
                elif len(recovered_string) < ui_state.window_width - len(prompt) - 1:
                    if key is not None and key.isprintable() and key < '\u0080':
                        recovered_string += key
                    elif key == ' ':
                        recovered_string += ' '
                    else:
                        continue
                else:
                    continue
                syntax_highlight_string(self, prompt = prompt, input_string = recovered_string, items = scan_recovered_string(recovered_string), in_place = True)
    else:
        return input(prompt).strip()
    print()
    return recovered_string.strip()

def re_print_fixed_terminal_prompt(self: Interface) -> str:
    x, y = save_current_cursor_pos(self)
    # x/y are `int | None` (get_cursor_position() returns (None, None) on a
    # failed ANSI position read -- see its own docstring/return below);
    # fall back to 0, the same convention used elsewhere in this file for a
    # failed read.
    x = x if x is not None else 0
    y = y if y is not None else 0
    move_cursor(self, x + len('prism> '), y - 1)
    return print_fixed_terminal_prompt(self).strip()

def print_twilio_terminal_prompt() -> str:
    print("Please enter your message below. Press ENTER to send.")
    return input(f"\n{green('twilio> ')}").strip()

def get_cursor_position() -> tuple[int | None, int | None]:
    sys.stdout.write("\033[6n")
    sys.stdout.flush()

    buf = ""
    with raw_mode():
        while True:
            ch = ""
            try:
                if kbhit():
                    ch = getwch()
                else:
                    time.sleep(0.01)  # avoid busy-waiting the CPU while idle
                    continue
            except Exception as e:
                error(f"Failed to read cursor position: {e}")
                return None, None
            buf += ch
            if ch == "R":
                break

    if not buf.startswith("\x1b["):
        return None, None  # not an ANSI response

    try:
        pos = buf[2:-1]  # strip "\x1b[" and trailing "R"
        row_str, col_str = pos.split(";")
        return int(col_str) - 1, int(row_str) - 1 
    except Exception as e:
        error(f"Failed to parse cursor position: {e}")
        return None, None
        
def save_current_cursor_pos(self: Interface) -> tuple[int | None, int | None]:
    x, y = get_cursor_position()
    save_cursor_pos(self, x, y)
    return x, y

def save_cursor_pos(self: Interface, x: int | None, y: int | None) -> None:
    if not hasattr(self, 'saved_positions'):
        self.saved_positions = []
    self.saved_positions.append((x, y))

def restore_cursor_pos(self: Interface, index: int = -1) -> None:
    if not hasattr(self, 'saved_positions') or not self.saved_positions:
        return
    x, y = self.saved_positions[index]
    move_cursor(self, x, y)

def move_cursor(self: Interface, x: int | None, y: int | None) -> None:
    try:
        # x/y may genuinely be None (e.g. a failed get_cursor_position()
        # read) -- unlike the flagged spots noted elsewhere in this file,
        # that's not a bug here: the arithmetic below is wrapped in this
        # try/except specifically to swallow that case (see the `except`
        # branch's debug-only message).
        sys.stdout.write(f"\033[{y+1};{x+1}H")  # type: ignore[operator]
        sys.stdout.flush()
    except Exception as e:
        if getattr(self, 'debug', False):
            print(f"error moving: {x if x is not None else 'None'}, {y if y is not None else 'None'}")

def clear_column(self: Interface, x: int, y: int, width: int, height: int) -> None:
    save_x, save_y = get_cursor_position()
    if save_x is not None and save_y is not None:
        save_cursor_pos(self, save_x, save_y)
    for row in range(height):
        move_cursor(self, x, y + row)
        sys.stdout.write(" " * width)
    restore_cursor_pos(self, 0)

def ansi_save_cursor() -> None:
    sys.stdout.write("\033[s")
    sys.stdout.flush()

def ansi_restore_cursor() -> None:
    sys.stdout.write("\033[u")
    sys.stdout.flush()

def ansi_clear_line() -> None:
    sys.stdout.write("\033[2K")
    sys.stdout.flush()

def ansi_clear_screen() -> None:
    sys.stdout.write("\033[2J")
    sys.stdout.flush()

def ansi_write_char(c: str) -> None:
    sys.stdout.write(c)
    sys.stdout.flush()

def ansi_hide_cursor() -> None:
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

def ansi_show_cursor() -> None:
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()

def ansi_write_str(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()

# def screen_write(self, content, initial_x, initial_y, column_width, window_height):

def assistant_header_write(self: Interface, lines: list[str]) -> None:
    import re

    lines = [line.encode().decode('unicode_escape') for line in lines]

    initial_x = 0
    initial_y = 3
    window_height = 1
    ansi_save_cursor()
    ansi_hide_cursor()

    clear_column(self, initial_x, initial_y, ui_state.window_width, 1)

    full_text = "\n".join(lines)
    ansi_escape = re.compile(r'\033\[[0-?]*[ -/]*[@-~]')

    matches = list(ansi_escape.finditer(full_text))
    next_escape_idx = 0
    next_escape = matches[next_escape_idx] if matches else None

    row = 0
    col = 0
    
    time_to_read_char_fast = 0.02
    time_to_read_char_medium = 0.04
    time_to_read_char_slow = 0.05
    min_time_to_read = 1
    max_time_to_read = 10
    print_speed = ui_state.assistant_type_speed

    i = 0
    length = len(full_text)

    with raw_mode():
        while i < length:
            if next_escape and i == next_escape.start():
                ansi_write_str(next_escape.group())
                i = next_escape.end()
                next_escape_idx += 1
                next_escape = matches[next_escape_idx] if next_escape_idx < len(matches) else None
                continue

            ch = full_text[i]

            if kbhit():
                key = getwch()
                if key == '\r':  # enter key
                    ansi_restore_cursor()
                    ansi_show_cursor()
                    return

            if ch == "\n" or col >= ui_state.window_width:
                row += 1
                if row >= window_height:
                    if col < 20:
                        char_time = time_to_read_char_slow
                    elif col < 50:
                        char_time = time_to_read_char_medium
                    else:
                        char_time = time_to_read_char_fast
                    text_reading_time = max(min_time_to_read, min(max_time_to_read, col * char_time))
                    time.sleep(text_reading_time)
                    if i < length - 1:
                        clear_column(self, initial_x, initial_y, ui_state.window_width, 1)
                    row = 0
                col = 0
                if ch == "\n":
                    i += 1
                    continue

            move_cursor(self, initial_x + col, initial_y + row)
            ansi_write_char(ch)
            time.sleep(print_speed)
            col += 1
            i += 1

    ansi_show_cursor()
    ansi_restore_cursor()

