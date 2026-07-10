"""Tests for utils/_menu_display.py.

`check_for_special_commands` is defined *inside* `print_menu_options` (a
closure) and can't be imported/called directly, so it's exercised
indirectly here by calling `print_menu_options(fake_interface, menu_options,
choice=<test string>)` and asserting on the resulting side effects, per
utils/CLAUDE.md's documented fragility: the 3 special-command prefixes
(`command `, `?`, `/`) are destructured
positionally from a list of booleans (_menu_display.py) -- these
tests pin each prefix to its correct behavior so a silent reordering bug
would be caught.

Passing `choice` explicitly (never None) is also what keeps these tests
non-interactive: `print_menu_options` only calls into the raw-terminal
prompt / column-rendering code (which needs a real TTY and, per
utils/CLAUDE.md, `get_cursor_position()` has no timeout on non-interactive
stdin) when `choice is None`.
"""
from collections import deque
from unittest.mock import MagicMock

import pytest

import user_interface_menus._menu_helper as _menu_helper
import user_interface_menus.utils._menu_display as _menu_display
from user_interface_menus.utils._menu_display import (
    infopage,
    invalid_choice_menu,
    print_global_command_menu,
    print_menu_options,
    print_recent_commands,
)
from user_interface_menus.utils._menu_navigation import ReturnToMainMenu


def _set_menu_options(options):
    _menu_helper._menu_options = options


# ------------------------------------------------------------
# check_for_special_commands, via print_menu_options(choice=...)
# ------------------------------------------------------------

def test_command_prefix_delegates_to_global_command_menu(fake_interface, monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(_menu_display, 'print_global_command_menu', mock)
    result = print_menu_options(fake_interface, {}, choice='command foo bar')
    assert result == 1
    mock.assert_called_once_with(fake_interface, 'foo bar')


def test_question_prefix_delegates_to_global_command_menu_with_query(fake_interface, monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(_menu_display, 'print_global_command_menu', mock)
    result = print_menu_options(fake_interface, {}, choice='?bar')
    assert result == 1
    mock.assert_called_once_with(fake_interface, 'bar')


def test_bare_question_mark_passes_none_query(fake_interface, monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(_menu_display, 'print_global_command_menu', mock)
    print_menu_options(fake_interface, {}, choice='?')
    mock.assert_called_once_with(fake_interface, None)


def test_slash_prefix_queues_chained_commands(fake_interface):
    result = print_menu_options(fake_interface, {}, choice='/cmd1/cmd2')
    assert result == 1
    assert list(fake_interface.commands_queue) == ['cmd1', 'cmd2']


def test_slash_prefix_with_iterations_repeats_command(fake_interface):
    print_menu_options(fake_interface, {}, choice='/cmd*3')
    assert list(fake_interface.commands_queue) == ['cmd', 'cmd', 'cmd']


def test_home_command_raises_return_to_main_menu(fake_interface):
    """The "home" global command is the fix for the recursive-menu-exit bug:
    it must propagate all the way out of print_menu_options as a
    ReturnToMainMenu (not get caught by print_menu_options' own outer
    try/except and converted into an error() call/return 0), so a caller
    several stack frames up (ultimately _main_menu.py::main_menu()) can
    catch it and redraw a fresh main menu in one shot.
    """
    with pytest.raises(ReturnToMainMenu):
        print_menu_options(fake_interface, {}, choice='home')


def test_home_is_exact_match_not_a_prefix(fake_interface, monkeypatch):
    """"home" is matched by exact equality, not startswith -- unlike the
    symbol-based prefixes below, so a menu option or typed word that merely
    starts with "home" (e.g. "homework") isn't swallowed by it."""
    monkeypatch.setattr(_menu_display, 'invalid_choice_menu', MagicMock())
    monkeypatch.setattr(_menu_display, 'syntax_highlight', MagicMock())
    _set_menu_options({})
    result = print_menu_options(fake_interface, {}, choice='homework')
    assert result == 0
    _menu_display.invalid_choice_menu.assert_called_once()


def test_no_matching_prefix_is_not_treated_as_special(fake_interface, monkeypatch):
    """A choice with none of the 3 prefixes must fall through
    check_for_special_commands (returns False) to ordinary menu-option
    resolution, not be swallowed as a special command.

    _menu_options is seeded to {} (not left None): check_global_menu_options
    unconditionally does `menu_options.get(query)` with no None-guard, so a
    still-None _menu_options (the real module's pristine state before
    load_menus() ever runs) raises AttributeError instead of returning None
    -- a real pre-existing gap, flagged in the session report rather than
    fixed here, since production code always calls load_menus() before any
    user input is possible (run_prism.py: load_params(); load_menus();
    PRISMInterface()) so it's unreachable in practice.
    """
    _set_menu_options({})
    monkeypatch.setattr(_menu_display, 'invalid_choice_menu', MagicMock())
    monkeypatch.setattr(_menu_display, 'syntax_highlight', MagicMock())
    result = print_menu_options(fake_interface, {}, choice='plainword')
    assert result == 0
    _menu_display.invalid_choice_menu.assert_called_once()


# ------------------------------------------------------------
# print_menu_options: ordinary (non-special) dispatch
# ------------------------------------------------------------

def test_empty_choice_with_submenu_returns_1_immediately(fake_interface):
    assert print_menu_options(fake_interface, {}, submenu=True, choice='') == 1


def test_empty_choice_without_submenu_reprompts_until_nonempty(fake_interface, monkeypatch):
    responses = iter(['', '', 'help'])
    monkeypatch.setattr(_menu_display, 'print_fixed_terminal_prompt', lambda self, submenu: next(responses))
    _set_menu_options({'help': {'description': 'Help', 'menu_caller': lambda self: True}})
    result = print_menu_options(fake_interface, {}, submenu=False, choice='')
    assert result == 1


def test_choice_matching_local_menu_option_invokes_its_caller(fake_interface):
    calls = []
    menu_options = {
        'local-opt': {'description': 'Local', 'menu_caller': lambda self: calls.append(self) or True},
    }
    result = print_menu_options(fake_interface, menu_options, choice='local-opt')
    assert result == 1
    assert calls == [fake_interface]
    assert 'local-opt' in _menu_helper.RECENT_COMMANDS


def test_choice_matching_global_menu_option_invokes_its_caller(fake_interface):
    calls = []
    _set_menu_options({
        'global-opt': {'description': 'Global', 'menu_caller': lambda self: calls.append(self) or True},
    })
    result = print_menu_options(fake_interface, {}, choice='global-opt')
    assert result == 1
    assert calls == [fake_interface]
    assert 'global-opt' in _menu_helper.RECENT_COMMANDS


def test_local_menu_option_takes_precedence_over_global(fake_interface):
    local_calls, global_calls = [], []
    _set_menu_options({
        'dup': {'description': 'Global dup', 'menu_caller': lambda self: global_calls.append(self) or True},
    })
    menu_options = {
        'dup': {'description': 'Local dup', 'menu_caller': lambda self: local_calls.append(self) or True},
    }
    print_menu_options(fake_interface, menu_options, choice='dup')
    assert local_calls == [fake_interface]
    assert global_calls == []


def test_unrecognized_choice_triggers_invalid_choice_menu(fake_interface, monkeypatch):
    mock_invalid = MagicMock()
    monkeypatch.setattr(_menu_display, 'invalid_choice_menu', mock_invalid)
    monkeypatch.setattr(_menu_display, 'syntax_highlight', MagicMock())
    _set_menu_options({})
    result = print_menu_options(fake_interface, {}, choice='nonexistent', submenu=True)
    assert result == 0
    mock_invalid.assert_called_once_with(fake_interface, {}, 'nonexistent', submenu=True)


# ------------------------------------------------------------
# print_global_command_menu
# ------------------------------------------------------------

def test_print_global_command_menu_sorts_when_query_is_none(fake_interface, monkeypatch):
    _set_menu_options({
        'zeta': {'description': 'z', 'menu_caller': lambda self: True},
        'alpha': {'description': 'a', 'menu_caller': lambda self: True},
    })
    captured = {}

    def fake_print_menu_options(self, menu_options, submenu=False, **kwargs):
        captured['menu_options'] = menu_options
        captured['submenu'] = submenu
        return True

    monkeypatch.setattr(_menu_display, 'print_menu_options', fake_print_menu_options)
    print_global_command_menu(fake_interface, query=None)
    assert list(captured['menu_options'].keys()) == ['alpha', 'zeta']
    assert captured['submenu'] is True


def test_print_global_command_menu_reports_no_matches(fake_interface, monkeypatch, capsys):
    _set_menu_options({'alpha': {'description': 'a', 'menu_caller': lambda self: True}})
    monkeypatch.setattr(_menu_display, 'print_menu_options', lambda self, menu_options, **k: True)
    print_global_command_menu(fake_interface, query='no-such-thing-zzz')
    assert 'No commands found matching your query.' in capsys.readouterr().out


# ------------------------------------------------------------
# print_recent_commands
# ------------------------------------------------------------

def test_print_recent_commands_empty_prints_message_and_exits(fake_interface, capsys):
    assert _menu_helper.RECENT_COMMANDS == []
    print_recent_commands(fake_interface)
    assert 'No recent commands found.' in capsys.readouterr().out


def test_print_recent_commands_empty_with_pending_chain_is_silent(fake_interface, capsys):
    fake_interface.commands_queue.append('something')
    print_recent_commands(fake_interface)
    assert capsys.readouterr().out == ''


def test_print_recent_commands_builds_menu_and_delegates(fake_interface, monkeypatch):
    _menu_helper.RECENT_COMMANDS.append('help')
    captured = {}

    def fake_print_menu_options(self, menu_options, submenu=False, **kwargs):
        captured['menu_options'] = menu_options
        return True

    monkeypatch.setattr(_menu_display, 'print_menu_options', fake_print_menu_options)
    print_recent_commands(fake_interface)
    assert 'help' in captured['menu_options']


# ------------------------------------------------------------
# invalid_choice_menu
# ------------------------------------------------------------

def test_invalid_choice_menu_no_candidates_prompts_help(fake_interface, monkeypatch, capsys):
    _set_menu_options({})
    # Must return non-empty immediately: invalid_choice_menu re-prompts in a
    # `while choice.strip() == '': ...` loop with no timeout, so an
    # empty-string stub would hang the test.
    monkeypatch.setattr(_menu_display, 'print_fixed_terminal_prompt', lambda self, submenu: 'no')
    monkeypatch.setattr(_menu_display, 'print_menu_options', lambda *a, **k: True)
    invalid_choice_menu(fake_interface, {}, choice='totallyunknown', submenu=True)
    out = capsys.readouterr().out
    assert 'Invalid choice.' in out


def test_invalid_choice_menu_yes_selects_first_suggestion(fake_interface, monkeypatch):
    calls = []
    _set_menu_options({
        'help': {'description': 'Help', 'menu_caller': lambda self: calls.append(self) or True},
    })
    monkeypatch.setattr(_menu_display, 'print_fixed_terminal_prompt', lambda self, submenu: 'yes')
    invalid_choice_menu(fake_interface, {}, choice='hlep', submenu=True)
    assert calls == [fake_interface]
    assert 'help' in _menu_helper.RECENT_COMMANDS


# ------------------------------------------------------------
# infopage
# ------------------------------------------------------------

def test_infopage_prints_content_lines_and_exits(fake_interface, capsys):
    infopage(fake_interface, content=['line one', 'line two'], title='My Page')
    out = capsys.readouterr().out
    assert 'line one' in out
    assert 'line two' in out


def test_infopage_no_content_reports_error(fake_interface, capsys):
    infopage(fake_interface, content=[], title='Empty Page')
    out = capsys.readouterr().out
    assert 'No content available for this infopage.' in out


def test_infopage_skips_output_when_commands_queue_pending(fake_interface, capsys):
    fake_interface.commands_queue.append('something')
    infopage(fake_interface, content=['should not print'], title='Page')
    assert capsys.readouterr().out == ''
