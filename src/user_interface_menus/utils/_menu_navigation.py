"""menu navigation logic"""

from typing import Any, Callable
from collections.abc import Iterable

from user_interface_menus.utils._display import *
# See _display.py's top-of-file comment for why `ui_state` is safe to import
# once here instead of re-importing inside every function body (it's a
# single mutable object whose attributes are updated in place, never
# rebound, so a reference taken here never goes stale) and why it's
# imported from _ui_state.py rather than _menu_helper.py (avoids a real
# circular import).
from user_interface_menus._ui_state import ui_state
from user_interface_menus._types import Interface, MenuOptions

# A menu_caller is either a callable taking the interface (`self`) and
# returning some truthy/falsy-ish result (see goto_menu()'s docstring/
# callers -- print_menu_options() and the main menu loop treat any truthy
# return as "handled"), or a `str` alias that goto_menu() resolves by
# looking it up in the global/local menu-options registries and recursing.
MenuCaller = Callable[..., Any] | str

class ReturnToMainMenu(Exception):
    """Raised by the global "home" command (see _menu_display.py's
    check_for_special_commands) to unwind the whole menu call stack back to
    the main menu in one shot, regardless of how many submenus deep the user
    currently is.

    Every blanket `except Exception` that sits between where this is raised
    and the top-level main_menu() loop must catch-and-reraise this first
    (`except ReturnToMainMenu: raise`) so it propagates instead of being
    swallowed and converted into an error() message -- see goto_menu() and
    process_chained_command() below, print_menu_options() in
    _menu_display.py (all three of its try/except blocks), and
    participant_management_menu() in
    participants/_participant_management_menus.py (the one other menu file
    that wraps its own menu-dispatch loop in a try/except). Caught for real
    only in _main_menu.py's main_menu().
    """
    pass

def menu_loop(
    self: Interface,
    menu_options: MenuOptions,
    header: str = "main",
    name: str = "Main Menu",
    submenu: bool = True,
    recommended_actions: list[str] = [],
    additional_content: list[str] | None = None,
) -> None:
    if 'print_menu_options' not in globals():
        from user_interface_menus.utils._menu_display import print_menu_options
    if (name == "Main Menu" or header == "main") and submenu:
        error("Please call menu loop with the appropriate parameters.", self)

    while True:
        if not self.commands_queue:
            print_menu_header(header)
            if additional_content:
                for line in additional_content:
                    if line == "-":
                        print_dashes()
                    elif line == "":
                        print()
                    else:
                        print(line)
            assistant_header_write(self, [name])
        if print_menu_options(self, menu_options, submenu = submenu, recommended_actions = recommended_actions) and submenu:
            break

def get_menu_options() -> MenuOptions:
    # Populated by load_menus() (see _menu_helper.py) before any menu
    # function that could reach here ever runs -- prism_interface.py's
    # `__main__` block always calls load_menus() before constructing
    # PRISMInterface(). Asserted (not silently `or {}`-defaulted) so a
    # genuine call-order bug fails loudly instead of behaving as if there
    # were simply no commands registered.
    assert ui_state.menu_options is not None, "get_menu_options() called before load_menus() populated the registry"
    return ui_state.menu_options

def get_relevant_menu_options(query: str | None = None, exact_match: bool = False) -> MenuOptions:
    from difflib import get_close_matches

    # `query` is threaded through explicitly as a parameter here (`str`,
    # not the enclosing `str | None`) rather than closed over, because
    # mypy doesn't carry the `if query is not None:` narrowing below into
    # nested-function closures -- see individual_participant_menu()'s
    # `participant`/`fetched_participant` split for the same pattern
    # elsewhere in this tree. Both nested functions are only ever actually
    # called from inside that narrowed block.
    def sort(iterable: Iterable[str], query: str) -> list[str]:
        threshold = max(ui_state.related_options_threshold, 0.1)
        return get_close_matches(query, iterable, n = 15, cutoff = threshold)

    def find_subset_matches(iterable: Iterable[str], query: str) -> list[str]:
        matches = []
        for item in iterable:
            if query in item:
                matches.append(item)
        return matches

    menu_options = get_menu_options()
    potential_global_choices = ', '.join(menu_options.keys())
    if query is None:
        choices = potential_global_choices

    if query is not None:
        if exact_match:
            if perfect_match := menu_options.get(query):
                return {query: perfect_match}

        choices = ', '.join(
            sorted(
            set(sort(set(potential_global_choices.split(', ')), query)) |
            set(find_subset_matches(potential_global_choices.split(', '), query))
            )
        )

    return {choice: menu_options[choice] for choice in choices.split(', ') if choice in menu_options}

def check_global_menu_options(query: str | None = None) -> tuple[str, Any] | None:
    # The second tuple element is the raw `menu_caller` value straight out
    # of the MenuOptions dict (declared `Any` there -- see _types.py) rather
    # than narrowed to MenuCaller: in every real menu_options dict in this
    # codebase it's always a callable, never the `str`-alias form MenuCaller
    # also allows (that form is only ever goto_menu()'s own top-level
    # argument, resolved by *looking up* one of these dict entries -- not
    # something stored as a dict value itself).
    if query is None:
        return None

    menu_options = get_menu_options()
    result = menu_options.get(query)
    if result is None:
        return None
    return result['description'], result['menu_caller']

def goto_menu(menu_caller: MenuCaller, self: Interface) -> Any:
    import time
    from user_interface_menus._menu_helper import get_local_menu_options, print_local_menu_options
    time.sleep(ui_state.menu_delay)
    try:
        if callable(menu_caller):
            return menu_caller(self)
        elif isinstance(menu_caller, str):
            global_result = check_global_menu_options(menu_caller)
            if global_result:
                description, caller = global_result
                return caller(self)

            local_results = get_local_menu_options()
            local_result = local_results.get(menu_caller)
            if local_result:
                menu_caller = local_result['menu_caller']
                if callable(menu_caller):
                    return menu_caller(self)
                elif isinstance(menu_caller, str):
                    return goto_menu(menu_caller, self)
            else:
                print_local_menu_options()
                error_string = f"likely a syntax error. {(yellow('?<query>'))} to search for commands."
                error(f"Command '{menu_caller}' failed; {error_string}", self)
                return False
        else:
            # Provably unreachable under MenuCaller's declared type
            # (Callable | str, both handled above) -- kept as defensive
            # code anyway, since `self`/`menu_caller` are duck-typed in
            # practice (see Interface's own docstring) and a caller passing
            # something else entirely wouldn't be caught by mypy at every
            # call site. Not a functional bug; narrow ignore rather than
            # deleting a real defensive branch.
            error("Invalid menu caller.", self)  # type: ignore[unreachable]
            return False
    except ReturnToMainMenu:
        raise
    except Exception as e:
        error(f"An error occurred while navigating to the menu: {e}", self)
        return False

def get_input(self: Interface, prompt: str | None = None, default_value: str | None = None, print_prompt: bool = True) -> Any:
    try:
        inputs_queue = self.inputs_queue
        # Provably unreachable under Interface's declared type
        # (PRISMInterface.__init__ always sets a real Queue) -- kept as
        # defensive code anyway for a duck-typed `self` that doesn't
        # strictly match (e.g. a test double). Narrow ignore, not a
        # functional bug.
        if inputs_queue is None:
            import queue  # type: ignore[unreachable]
            self.inputs_queue = queue.Queue()

        if inputs_queue and not inputs_queue.empty():
            input_override = inputs_queue.get()
            if input_override is not None:
                if print_prompt:
                    print(f"{prompt}{input_override}")
                return input_override
        
        if prompt is None:
            prompt = "Input: "
        prompt += f"[default = {default_value}]: " if default_value else ""
        
        user_input = input(prompt).strip()
        if not user_input and default_value is not None:
            return default_value
        return user_input
    except Exception as e:
        error(f"An error occurred while getting input: {e}", self)
        return None

def prompt_confirmation(self: Interface, prompt: str = "Are you sure?", default_value: str = "n") -> bool:
    confirmation = get_input(self, prompt + ' (y/n): ', default_value)
    if confirmation.lower() in ['y', 'yes']:
        return True
    elif confirmation.lower() in ['n', 'no']:
        return False
    else:
        print(f"Invalid confirmation input. Defaulting to {default_value}.")
        return default_value.lower() in ['y', 'yes']

def clear_inputs_queue(self: Interface) -> None:
    from queue import Empty
    inputs_queue = self.inputs_queue
    # Provably unreachable under Interface's declared type -- same
    # duck-typing defensiveness as get_input() above; narrow ignore, not a
    # functional bug.
    if inputs_queue is None:
        error("Inputs queue is not available.", self)  # type: ignore[unreachable]
        return

    try:
        while True:
            inputs_queue.get_nowait()
    except Empty:
        pass

def clear_commands_queue(self: Interface) -> None:
    commands_queue = self.commands_queue
    # Provably unreachable under Interface's declared type -- same
    # duck-typing defensiveness as get_input() above; narrow ignore, not a
    # functional bug.
    if commands_queue is None:
        error("Commands queue is not available.")  # type: ignore[unreachable]
        return
    
    try:
        while True:
            commands_queue.popleft()
    except IndexError:
        pass  # empty

class CommandInjector:
    def __init__(self, command_string: str) -> None:
        self.command_string = command_string

    def __call__(self, self_ref: Interface) -> bool:
        try:
            tokens = self.command_string.split('/')
            for token in reversed(tokens):
                stripped = token.strip()
                if stripped:
                    self_ref.commands_queue.appendleft(stripped)
        except Exception as e:
            # FLAGGED, NOT FIXED (see mypy-adoption report): `self` here is
            # this CommandInjector instance (it's `__call__`'s own first
            # parameter), not the PRISMInterface `self_ref` -- error()
            # expects an Interface-like object and, when given one, calls
            # clear_commands_queue(self) on it, which would AttributeError
            # on a CommandInjector (no `commands_queue` attribute), inside
            # an already-executing exception handler. Pre-existing bug, not
            # introduced by adding types; left as-is (only silenced for
            # mypy) per instructions not to change runtime behavior while
            # annotating.
            error(f"Error processing command string: {e}", self)  # type: ignore[arg-type]
        finally:
            return True

    def __repr__(self) -> str:
        return f"<CommandInjector: {self.command_string}>"

def process_chained_command(self: Interface) -> int:
    import time
    commands = self.commands_queue
    inputs = self.inputs_queue
    # Predefine `command` so the `except Exception as e:` handler below can
    # always reference it in its error message, even if commands.popleft()
    # itself raises (empty queue) before `command` would otherwise be
    # assigned. Previously this didn't matter -- referencing the undefined
    # name raised a *second* exception (UnboundLocalError) while already
    # handling the first, but the old `finally: return 1` unconditionally
    # swallowed whatever was propagating, masking it. Now that `finally`
    # only clears the inputs queue (see ReturnToMainMenu handling below), a
    # real second exception here would propagate uncaught instead.
    command = None
    try:
        command = commands.popleft()
        time.sleep(ui_state.menu_delay)
        if not command:
            raise ValueError("Command cannot be empty.")
        if '?' in command:
            parts = command.split('?', 1)
            print(f"Executing command: {parts[0]}")
            command = parts[0]
            input_value = parts[1] if len(parts) > 1 else ""
            input_values = input_value.split('?')
            print(f"Input values: {input_values}")
            for value in input_values:
                inputs.put(value.strip())
        else:
            print(f"Executing command: {command}")
        goto_menu(command, self)
        return 1
    except ReturnToMainMenu:
        # No `return` (or `break`/`continue`) may appear in the `finally`
        # below while this is propagating -- a `return` in `finally` always
        # wins over an in-flight exception/return from the `try`/`except`
        # above it (a general Python gotcha, not specific to this
        # exception), which would silently swallow "home" here and convert
        # it into a normal `return 1` instead of unwinding to the main menu.
        raise
    except Exception as e:
        error(f"Error processing command '{command}': {e}", self)
        return 1
    finally:
        clear_inputs_queue(self)