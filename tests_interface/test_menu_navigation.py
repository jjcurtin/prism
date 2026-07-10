"""Tests for utils/_menu_navigation.py: get_relevant_menu_options/
check_global_menu_options (fuzzy search over the _menu_helper._menu_options
global), goto_menu (the central dispatcher), get_input/prompt_confirmation
(queue-override input), the queue-clearing helpers, CommandInjector, and
process_chained_command.
"""
from collections import deque

import pytest

import user_interface_menus._menu_helper as _menu_helper
from user_interface_menus.utils._menu_navigation import (
    CommandInjector,
    ReturnToMainMenu,
    check_global_menu_options,
    clear_commands_queue,
    clear_inputs_queue,
    get_input,
    get_menu_options,
    get_relevant_menu_options,
    goto_menu,
    process_chained_command,
    prompt_confirmation,
)


# ------------------------------------------------------------
# get_menu_options / get_relevant_menu_options / check_global_menu_options
# ------------------------------------------------------------

def _set_menu_options(options):
    _menu_helper._menu_options = options


def test_get_menu_options_reads_current_global():
    options = {'help': {'description': 'Help', 'menu_caller': lambda self: True}}
    _set_menu_options(options)
    assert get_menu_options() is options


def test_get_relevant_menu_options_query_none_returns_all():
    options = {
        'help': {'description': 'Help', 'menu_caller': lambda self: True},
        'tasks': {'description': 'Tasks', 'menu_caller': lambda self: True},
    }
    _set_menu_options(options)
    result = get_relevant_menu_options(None)
    assert result == options


def test_get_relevant_menu_options_exact_match_short_circuits():
    caller = lambda self: True
    options = {
        'tasks': {'description': 'Tasks', 'menu_caller': caller},
        'tasks add': {'description': 'Add task', 'menu_caller': caller},
    }
    _set_menu_options(options)
    result = get_relevant_menu_options('tasks', exact_match=True)
    assert result == {'tasks': options['tasks']}


def test_get_relevant_menu_options_exact_match_miss_falls_back_to_fuzzy():
    caller = lambda self: True
    options = {
        'tasks': {'description': 'Tasks', 'menu_caller': caller},
        'tasks add': {'description': 'Add task', 'menu_caller': caller},
        'shutdown': {'description': 'Shutdown', 'menu_caller': caller},
    }
    _set_menu_options(options)
    # 'taskss' doesn't exactly match any key, so exact_match=True should
    # fall through to the fuzzy/subset-match path rather than returning {}.
    result = get_relevant_menu_options('taskss', exact_match=True)
    assert 'tasks' in result
    assert 'shutdown' not in result


def test_get_relevant_menu_options_subset_match():
    caller = lambda self: True
    options = {
        'tasks': {'description': 'Tasks', 'menu_caller': caller},
        'tasks add': {'description': 'Add task', 'menu_caller': caller},
        'shutdown': {'description': 'Shutdown', 'menu_caller': caller},
    }
    _set_menu_options(options)
    result = get_relevant_menu_options('tasks')
    assert 'tasks' in result
    assert 'tasks add' in result
    assert 'shutdown' not in result


def test_check_global_menu_options_none_query_returns_none():
    assert check_global_menu_options(None) is None


def test_check_global_menu_options_unknown_query_returns_none():
    _set_menu_options({'help': {'description': 'Help', 'menu_caller': lambda self: True}})
    assert check_global_menu_options('nope') is None


def test_check_global_menu_options_known_query_returns_tuple():
    caller = lambda self: True
    _set_menu_options({'help': {'description': 'Help', 'menu_caller': caller}})
    result = check_global_menu_options('help')
    assert result == ('Help', caller)


# ------------------------------------------------------------
# goto_menu
# ------------------------------------------------------------

def test_goto_menu_callable_invoked_with_self(fake_interface):
    calls = []

    def caller(self):
        calls.append(self)
        return 'result'

    assert goto_menu(caller, fake_interface) == 'result'
    assert calls == [fake_interface]


def test_goto_menu_string_resolves_via_global_options(fake_interface):
    calls = []
    _set_menu_options({'help': {'description': 'Help', 'menu_caller': lambda self: calls.append(self) or True}})
    assert goto_menu('help', fake_interface) is True
    assert calls == [fake_interface]


def test_goto_menu_string_resolves_via_local_callable(fake_interface, monkeypatch):
    calls = []
    _set_menu_options({})  # no global match, forces local lookup
    monkeypatch.setattr(
        _menu_helper, 'get_local_menu_options',
        lambda: {'sub': {'description': 'Sub', 'menu_caller': lambda self: calls.append(self) or 'local'}},
    )
    assert goto_menu('sub', fake_interface) == 'local'
    assert calls == [fake_interface]


def test_goto_menu_string_resolves_via_local_string_recurses(fake_interface, monkeypatch):
    calls = []
    _set_menu_options({'help': {'description': 'Help', 'menu_caller': lambda self: calls.append(self) or 'via-global'}})
    monkeypatch.setattr(
        _menu_helper, 'get_local_menu_options',
        lambda: {'alias': {'description': 'Alias for help', 'menu_caller': 'help'}},
    )
    assert goto_menu('alias', fake_interface) == 'via-global'
    assert calls == [fake_interface]


def test_goto_menu_unresolvable_string_returns_false(fake_interface, monkeypatch):
    _set_menu_options({})
    monkeypatch.setattr(_menu_helper, 'get_local_menu_options', lambda: {})
    assert goto_menu('does-not-exist', fake_interface) is False


def test_goto_menu_invalid_type_returns_false(fake_interface):
    assert goto_menu(12345, fake_interface) is False


def test_goto_menu_exception_in_caller_is_caught(fake_interface):
    def caller(self):
        raise RuntimeError('boom')

    assert goto_menu(caller, fake_interface) is False


def test_goto_menu_propagates_return_to_main_menu_instead_of_swallowing(fake_interface):
    """Contrast with test_goto_menu_exception_in_caller_is_caught above: an
    ordinary exception raised by a menu_caller is caught and converted to
    False, but ReturnToMainMenu (the "home" command's unwind signal) must
    NOT be -- it needs to propagate through goto_menu's try/except
    (`except ReturnToMainMenu: raise`, ahead of the blanket `except
    Exception`) so a "home" raised arbitrarily deep in a nested submenu call
    reaches _main_menu.py::main_menu() instead of being reported as
    "An error occurred while navigating to the menu".
    """
    def caller(self):
        raise ReturnToMainMenu()

    with pytest.raises(ReturnToMainMenu):
        goto_menu(caller, fake_interface)


# ------------------------------------------------------------
# get_input / prompt_confirmation
# ------------------------------------------------------------

def test_get_input_returns_queued_value_without_calling_input(fake_interface, monkeypatch):
    fake_interface.inputs_queue.put('queued-value')

    def blow_up(*a, **k):
        raise AssertionError('input() should not be called when the queue has a value')

    monkeypatch.setattr('builtins.input', blow_up)
    assert get_input(fake_interface, prompt='Enter: ') == 'queued-value'


def test_get_input_prints_prompt_and_value_when_print_prompt_true(fake_interface, capsys):
    fake_interface.inputs_queue.put('abc')
    get_input(fake_interface, prompt='Enter: ', print_prompt=True)
    out = capsys.readouterr().out
    assert 'Enter: abc' in out


def test_get_input_does_not_print_when_print_prompt_false(fake_interface, capsys):
    fake_interface.inputs_queue.put('abc')
    get_input(fake_interface, prompt='Enter: ', print_prompt=False)
    out = capsys.readouterr().out
    assert out == ''


def test_get_input_falls_back_to_builtin_input_and_default(fake_interface, monkeypatch):
    monkeypatch.setattr('builtins.input', lambda prompt='': '')
    result = get_input(fake_interface, prompt='Enter: ', default_value='fallback')
    assert result == 'fallback'


def test_get_input_falls_back_to_builtin_input_typed_value(fake_interface, monkeypatch):
    monkeypatch.setattr('builtins.input', lambda prompt='': '  typed  ')
    result = get_input(fake_interface, prompt='Enter: ')
    assert result == 'typed'


def test_get_input_creates_queue_when_none(fake_interface, monkeypatch):
    fake_interface.inputs_queue = None
    monkeypatch.setattr('builtins.input', lambda prompt='': 'from-input')
    result = get_input(fake_interface, prompt='Enter: ')
    assert result == 'from-input'
    import queue as queue_module
    assert isinstance(fake_interface.inputs_queue, queue_module.Queue)


@pytest.mark.parametrize('answer,expected', [('y', True), ('yes', True), ('n', False), ('no', False)])
def test_prompt_confirmation_valid_answers(fake_interface, answer, expected):
    fake_interface.inputs_queue.put(answer)
    assert prompt_confirmation(fake_interface) is expected


def test_prompt_confirmation_invalid_answer_defaults(fake_interface, capsys):
    fake_interface.inputs_queue.put('maybe')
    result = prompt_confirmation(fake_interface, default_value='y')
    assert result is True
    assert 'Invalid confirmation input' in capsys.readouterr().out


# ------------------------------------------------------------
# clear_inputs_queue / clear_commands_queue
# ------------------------------------------------------------

def test_clear_inputs_queue_empties_queue(fake_interface):
    fake_interface.inputs_queue.put('a')
    fake_interface.inputs_queue.put('b')
    clear_inputs_queue(fake_interface)
    assert fake_interface.inputs_queue.empty()


def test_clear_inputs_queue_none_reports_error_without_raising(fake_interface):
    fake_interface.inputs_queue = None
    clear_inputs_queue(fake_interface)  # must not raise (input() is patched)


def test_clear_commands_queue_empties_deque(fake_interface):
    fake_interface.commands_queue.extend(['a', 'b', 'c'])
    clear_commands_queue(fake_interface)
    assert len(fake_interface.commands_queue) == 0


def test_clear_commands_queue_none_reports_error_without_raising(fake_interface):
    fake_interface.commands_queue = None
    clear_commands_queue(fake_interface)  # must not raise


# ------------------------------------------------------------
# CommandInjector
# ------------------------------------------------------------

def test_command_injector_pushes_tokens_in_original_order(fake_interface):
    CommandInjector('cmd1/cmd2/cmd3')(fake_interface)
    assert list(fake_interface.commands_queue) == ['cmd1', 'cmd2', 'cmd3']


def test_command_injector_skips_empty_tokens(fake_interface):
    CommandInjector('cmd1//cmd2/ /cmd3')(fake_interface)
    assert list(fake_interface.commands_queue) == ['cmd1', 'cmd2', 'cmd3']


def test_command_injector_prepends_to_existing_queue(fake_interface):
    fake_interface.commands_queue.append('later')
    CommandInjector('first/second')(fake_interface)
    assert list(fake_interface.commands_queue) == ['first', 'second', 'later']


def test_command_injector_swallows_exceptions_and_still_returns_true():
    """Documents current (intentional-looking, not fixed here) behavior:
    CommandInjector.__call__ catches its own exceptions and its `finally`
    unconditionally `return`s True, so a broken self_ref/queue silently
    reports success instead of propagating. See
    src/user_interface_menus/utils/_menu_navigation.py:186-196.
    """
    class BrokenSelf:
        @property
        def commands_queue(self):
            raise RuntimeError('queue unavailable')

    injector = CommandInjector('cmd1/cmd2')
    assert injector(BrokenSelf()) is True


def test_command_injector_repr():
    assert repr(CommandInjector('cmd1/cmd2')) == '<CommandInjector: cmd1/cmd2>'


# ------------------------------------------------------------
# process_chained_command
# ------------------------------------------------------------

def test_process_chained_command_runs_next_command(fake_interface):
    calls = []
    _set_menu_options({'help': {'description': 'Help', 'menu_caller': lambda self: calls.append(self) or True}})
    fake_interface.commands_queue.append('help')
    result = process_chained_command(fake_interface)
    assert result == 1
    assert calls == [fake_interface]


def test_process_chained_command_splits_input_values_into_inputs_queue(fake_interface, capsys):
    """The '?'-separated input values do get `.put()` onto inputs_queue
    (see _menu_navigation.py:211-219) -- but process_chained_command's
    `finally: clear_inputs_queue(self)` drains that same queue again before
    returning, on every call, success or not. So by the time the call
    returns there's nothing left to observe on the queue itself; assert on
    the print instead, and separately confirm the queue ends up empty.
    """
    _set_menu_options({'echo': {'description': 'Echo', 'menu_caller': lambda self: True}})
    fake_interface.commands_queue.append('echo?one?two')
    process_chained_command(fake_interface)
    out = capsys.readouterr().out
    assert "Input values: ['one', 'two']" in out
    assert fake_interface.inputs_queue.empty()


def test_process_chained_command_always_returns_1_even_when_goto_menu_fails(fake_interface):
    """goto_menu('unknown-command', ...) returns False (unresolvable), but
    process_chained_command unconditionally returns 1 for it anyway (an
    explicit `return 1` follows the `goto_menu(...)` call regardless of its
    result) -- the caller can't tell success from failure just from the
    return value -- documented, matching the analogous CommandInjector
    behavior above.
    """
    _set_menu_options({})
    fake_interface.commands_queue.append('unknown-command')
    result = process_chained_command(fake_interface)
    assert result == 1


def test_process_chained_command_clears_inputs_queue_on_success(fake_interface):
    _set_menu_options({'help': {'description': 'Help', 'menu_caller': lambda self: True}})
    fake_interface.inputs_queue.put('leftover')
    fake_interface.commands_queue.append('help')
    process_chained_command(fake_interface)
    assert fake_interface.inputs_queue.empty()


def test_process_chained_command_empty_queue_returns_1_without_raising(fake_interface):
    """commands_queue.popleft() on an empty deque raises IndexError before
    `command` would otherwise be assigned. `command` is now predefined
    (`= None`) ahead of the try block specifically so the `except Exception`
    handler's error message can safely reference it instead of raising a
    *second* exception (UnboundLocalError) while already handling the
    IndexError -- fixed as part of the 2026-07-10 ReturnToMainMenu/"home"
    work, which also removed the `finally: return 1` that used to
    unconditionally swallow any in-flight exception (including that second
    one) regardless of what caused it. See
    src/user_interface_menus/utils/_menu_navigation.py.
    """
    assert len(fake_interface.commands_queue) == 0
    result = process_chained_command(fake_interface)
    assert result == 1


def test_process_chained_command_empty_command_string_raises_value_error_internally(fake_interface):
    fake_interface.commands_queue.append('')
    result = process_chained_command(fake_interface)
    assert result == 1  # handled by `except Exception as e: ...; return 1`


# ------------------------------------------------------------
# ReturnToMainMenu / "home" command
# ------------------------------------------------------------

def test_process_chained_command_propagates_return_to_main_menu(fake_interface):
    """A "home"-triggering menu_caller reached via command chaining must
    also unwind past process_chained_command's try/except/finally, not get
    swallowed into a normal `return 1` the way an ordinary exception would.
    """
    def caller(self):
        raise ReturnToMainMenu()

    _set_menu_options({'boom': {'description': 'Boom', 'menu_caller': caller}})
    fake_interface.inputs_queue.put('leftover')
    fake_interface.commands_queue.append('boom')

    with pytest.raises(ReturnToMainMenu):
        process_chained_command(fake_interface)

    # the `finally` clause's cleanup still runs during unwinding
    assert fake_interface.inputs_queue.empty()


def test_home_from_three_levels_deep_returns_to_main_menu_in_one_shot(fake_interface, monkeypatch):
    """End-to-end regression test for the recursive-menu-exit bug: each
    submenu (main -> tasks -> tasks/add) runs its own `menu_loop`-style
    `while True: ... if print_menu_options(...): break` as a directly
    nested Python call (goto_menu -> menu_caller(self)), so previously
    backing out required one ENTER per level. Confirms that typing "home"
    from the deepest level (tasks/add) returns control to the main menu in
    a single typed command, not N separate ENTER-equivalent inputs -- by
    driving three real, unmodified menu functions (main_menu,
    system_task_menu, add_task_menu) through a scripted sequence of
    `print_fixed_terminal_prompt` responses and recording exactly which
    menu headers get (re)drawn, in order.
    """
    import user_interface_menus._main_menu as main_menu_module
    import user_interface_menus.utils._menu_display as _menu_display
    import user_interface_menus.utils._menu_navigation as _menu_navigation
    import user_interface_menus.tasks._add_task_menus as atm
    import user_interface_menus.tasks._system_task_menu as stm
    from user_interface_menus._main_menu import main_menu

    headers_shown = []
    monkeypatch.setattr(_menu_navigation, 'print_menu_header', lambda title: headers_shown.append(title))
    monkeypatch.setattr(stm, 'print_menu_header', lambda title: headers_shown.append(title))
    monkeypatch.setattr(atm, 'print_menu_header', lambda title: headers_shown.append(title))
    monkeypatch.setattr(_menu_navigation, 'assistant_header_write', lambda *a, **k: None)
    monkeypatch.setattr(stm, 'assistant_header_write', lambda *a, **k: None)

    responses = iter(['tasks', 'add', 'home', 'exit'])
    monkeypatch.setattr(_menu_display, 'print_fixed_terminal_prompt', lambda self, submenu: next(responses))

    def fake_exit(self):
        raise SystemExit(0)

    monkeypatch.setattr(main_menu_module, 'exit_interface', fake_exit)

    with pytest.raises(SystemExit):
        main_menu(fake_interface)

    # 'main' (startup) -> 'tasks' -> 'tasks add' -> 'main' again, straight
    # back from the deepest level after a single "home", then 'exit' is
    # resolved at that (correctly main-menu-level) redraw -- not, e.g., two
    # more 'main' redraws (which repeated single-level ENTER-style unwinding
    # would have produced) and not a repeat of 'tasks'/'tasks add'.
    assert headers_shown == ['main', 'tasks', 'tasks add', 'main']
