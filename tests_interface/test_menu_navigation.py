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
    `finally: clear_inputs_queue(self); return 1` (see gotcha docs on
    process_chained_command below) drains that same queue again before
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
    process_chained_command's `finally: return 1` means the caller can't
    tell success from failure just from the return value -- documented,
    matching the analogous CommandInjector behavior above.
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
    """Real, pre-existing quirk (not fixed here -- flagged in the test
    session report): commands_queue.popleft() on an empty deque raises
    IndexError before `command` is ever assigned. The `except` handler then
    references the (still-undefined) `command` name while building its
    error message, raising UnboundLocalError *while already handling*
    the IndexError. That new exception propagates into the `finally`
    block -- but `finally: return 1` unconditionally swallows any
    in-flight exception, so this never surfaces to the caller; it just
    silently returns 1. See
    src/user_interface_menus/utils/_menu_navigation.py:201-228.
    """
    assert len(fake_interface.commands_queue) == 0
    result = process_chained_command(fake_interface)
    assert result == 1


def test_process_chained_command_empty_command_string_raises_value_error_internally(fake_interface):
    fake_interface.commands_queue.append('')
    result = process_chained_command(fake_interface)
    assert result == 1  # swallowed by the same finally: return 1 pattern
