"""Tests for user_interface_menus/tasks/: _system_task_menu.py,
_execute_task_menus.py, _add_task_menus.py.

Same conventions as test_participant_menus.py: `self.api` is replaced with a
MagicMock per test; outer `while True: ... if print_menu_options(...): break`
wrapper loops (system_task_menu, execute_menu, add_task_menu) are driven by
monkeypatching each module's own `print_menu_options` name to return True
immediately. Those three wrappers only gate `print_menu_header` behind
`not self.commands_queue` (no assistant_header_write / task-schedule print
entangled with it here, unlike the participant menu), so it's stubbed
directly rather than juggling commands_queue.

`self.get_task_types()` is a method on the real PRISMInterface (see
src/prism_interface.py) that FakeInterface doesn't define; tests that need it
set `fake_interface.get_task_types` as a plain instance-attribute MagicMock.
"""
from collections import deque
from unittest.mock import MagicMock

import pytest

import user_interface_menus._menu_helper as menu_helper
import user_interface_menus.tasks._add_task_menus as atm
import user_interface_menus.tasks._execute_task_menus as etm
import user_interface_menus.tasks._system_task_menu as stm


@pytest.fixture(autouse=True)
def _no_log_file(monkeypatch):
    monkeypatch.setattr(menu_helper, 'write_to_interface_log', lambda msg: None)


@pytest.fixture(autouse=True)
def _no_terminal_header(monkeypatch):
    monkeypatch.setattr(stm, 'print_menu_header', lambda *a, **k: None)
    monkeypatch.setattr(stm, 'assistant_header_write', lambda *a, **k: None)
    monkeypatch.setattr(etm, 'print_menu_header', lambda *a, **k: None)
    monkeypatch.setattr(atm, 'print_menu_header', lambda *a, **k: None)


# ------------------------------------------------------------
# print_task_schedule
# ------------------------------------------------------------

def test_print_task_schedule_prints_formatted_lines(fake_interface, capsys):
    fake_interface.api = MagicMock(return_value=(True, {'tasks': [
        {'task_type': 'ema', 'task_time': '16:00:00', 'r_script_path': None, 'run_today': True},
        {'task_type': 'RUN_R_SCRIPT', 'task_time': '02:00:00', 'r_script_path': 'foo.R'},
    ]}))
    stm.print_task_schedule(fake_interface)
    out = capsys.readouterr().out
    assert '1: ema @ 16:00:00 - Run Today: True' in out
    assert '2: RUN_R_SCRIPT @ 02:00:00 foo.R - Run Today: False' in out


def test_print_task_schedule_no_tasks_key(fake_interface, capsys):
    fake_interface.api = MagicMock(return_value=(True, {'other': []}))
    stm.print_task_schedule(fake_interface)
    assert 'No tasks scheduled.' in capsys.readouterr().out


def test_print_task_schedule_empty_tasks_list(fake_interface, capsys):
    fake_interface.api = MagicMock(return_value=(True, {'tasks': []}))
    stm.print_task_schedule(fake_interface)
    assert 'No tasks scheduled.' in capsys.readouterr().out


def test_print_task_schedule_api_failure(fake_interface, capsys):
    fake_interface.api = MagicMock(return_value=(False, None))
    stm.print_task_schedule(fake_interface)
    assert 'No tasks scheduled.' in capsys.readouterr().out


# ------------------------------------------------------------
# remove_task_menu
# ------------------------------------------------------------

def test_remove_task_menu_valid_index_success(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])  # skip header/print_task_schedule preamble
    task = {'task_type': 'ema', 'task_time': '16:00:00'}
    fake_interface.api = MagicMock(side_effect=[(True, {'tasks': [task]}), (True, True)])
    fake_interface.inputs_queue.put('1')

    stm.remove_task_menu(fake_interface)

    fake_interface.api.assert_any_call('DELETE', 'system/remove_system_task/ema/16:00:00')
    assert 'Task removed.' in capsys.readouterr().out


def test_remove_task_menu_valid_index_api_failure(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    task = {'task_type': 'ema', 'task_time': '16:00:00'}
    fake_interface.api = MagicMock(side_effect=[(True, {'tasks': [task]}), (False, None)])
    fake_interface.inputs_queue.put('1')

    stm.remove_task_menu(fake_interface)

    assert 'Failed to remove task.' in capsys.readouterr().out


def test_remove_task_menu_out_of_range_index(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    task = {'task_type': 'ema', 'task_time': '16:00:00'}
    fake_interface.api = MagicMock(return_value=(True, {'tasks': [task]}))
    fake_interface.inputs_queue.put('5')

    stm.remove_task_menu(fake_interface)

    assert 'Invalid index.' in capsys.readouterr().out


def test_remove_task_menu_non_numeric_index(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    task = {'task_type': 'ema', 'task_time': '16:00:00'}
    fake_interface.api = MagicMock(return_value=(True, {'tasks': [task]}))
    fake_interface.inputs_queue.put('abc')

    stm.remove_task_menu(fake_interface)

    assert 'Invalid input. Please enter a valid task index.' in capsys.readouterr().out


def test_remove_task_menu_no_tasks_scheduled(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(return_value=(True, {'tasks': []}))

    stm.remove_task_menu(fake_interface)

    assert 'No tasks scheduled to remove.' in capsys.readouterr().out


def test_remove_task_menu_outer_exception_reported_accurately(fake_interface, capsys):
    """Regression test for a fixed bug: tasks/_system_task_menu.py's
    remove_task_menu wraps its whole body in one
    `try: ... except Exception as e: error(...)`. The outer handler's
    message used to say "Invalid input: {e}" regardless of cause, which was
    fine for the inner int(index) ValueError it's clearly meant to catch,
    but misleading for any other exception (e.g. a real network failure
    surfaced by self.api raising). Now the outer message doesn't claim
    "invalid input" for a non-input-related failure.
    """
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(side_effect=RuntimeError('connection reset'))

    stm.remove_task_menu(fake_interface)

    out = capsys.readouterr().out
    assert 'connection reset' in out
    assert 'Invalid input' not in out


# ------------------------------------------------------------
# clear_task_schedule_menu
# ------------------------------------------------------------

def test_clear_task_schedule_menu_confirmed_success(fake_interface, capsys):
    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(True, True))
    stm.clear_task_schedule_menu(fake_interface)
    fake_interface.api.assert_called_once_with('DELETE', 'system/clear_task_schedule')
    assert 'Task schedule cleared.' in capsys.readouterr().out


def test_clear_task_schedule_menu_confirmed_failure(fake_interface, capsys):
    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(False, None))
    stm.clear_task_schedule_menu(fake_interface)
    assert 'Failed to clear task schedule.' in capsys.readouterr().out


def test_clear_task_schedule_menu_not_confirmed(fake_interface, capsys):
    fake_interface.inputs_queue.put('n')
    fake_interface.api = MagicMock()
    stm.clear_task_schedule_menu(fake_interface)
    fake_interface.api.assert_not_called()
    assert 'Task schedule not cleared.' in capsys.readouterr().out


# ------------------------------------------------------------
# system_task_menu (outer wrapper wiring)
# ------------------------------------------------------------

def test_system_task_menu_options_wired_correctly(fake_interface, monkeypatch):
    fake_interface.commands_queue = deque(['x'])  # skip print_task_schedule() preamble call too
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(stm, 'print_menu_options', mock_pmo)

    stm.system_task_menu(fake_interface)

    menu_options = mock_pmo.call_args[0][1]
    assert menu_options['add']['menu_caller'] is atm.add_task_menu
    assert menu_options['remove']['menu_caller'] is stm.remove_task_menu
    assert menu_options['execute']['menu_caller'] is etm.execute_menu
    assert menu_options['clear']['menu_caller'] is stm.clear_task_schedule_menu


# ------------------------------------------------------------
# execute_r_script_menu
# ------------------------------------------------------------

def test_execute_r_script_menu_no_scripts_errors(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(return_value=(False, None))
    etm.execute_r_script_menu(fake_interface)
    assert 'No R scripts available.' in capsys.readouterr().out


def test_execute_r_script_menu_valid_selection_success(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(side_effect=[
        (True, {'r_script_tasks': {'analyze': 'scripts/analyze'}}),
        (True, True),
    ])
    fake_interface.inputs_queue.put('1')

    etm.execute_r_script_menu(fake_interface)

    fake_interface.api.assert_any_call('POST', 'system/execute_r_script_task/scripts/analyze.R')
    assert 'R script task analyze executed.' in capsys.readouterr().out


def test_execute_r_script_menu_valid_selection_failure(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(side_effect=[
        (True, {'r_script_tasks': {'analyze': 'scripts/analyze'}}),
        (False, None),
    ])
    fake_interface.inputs_queue.put('1')

    etm.execute_r_script_menu(fake_interface)

    assert 'Failed to execute R script task analyze.' in capsys.readouterr().out


def test_execute_r_script_menu_invalid_index(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(return_value=(True, {'r_script_tasks': {'analyze': 'scripts/analyze'}}))
    fake_interface.inputs_queue.put('99')

    etm.execute_r_script_menu(fake_interface)

    assert 'Invalid index.' in capsys.readouterr().out


# ------------------------------------------------------------
# execute_task_menu
# ------------------------------------------------------------

def test_execute_task_menu_no_task_types_errors(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={})
    etm.execute_task_menu(fake_interface)
    assert 'No task types available.' in capsys.readouterr().out


def test_execute_task_menu_run_r_script_delegates(fake_interface, monkeypatch):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={'RUN_R_SCRIPT': 'Run R Script'})
    fake_interface.inputs_queue.put('1')
    calls = []
    monkeypatch.setattr(etm, 'execute_r_script_menu', lambda self: calls.append(self))

    etm.execute_task_menu(fake_interface)

    assert calls == [fake_interface]


def test_execute_task_menu_success(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={'SEND_EMA': 'Send EMA'})
    fake_interface.inputs_queue.put('1')
    fake_interface.api = MagicMock(return_value=(True, True))

    etm.execute_task_menu(fake_interface)

    fake_interface.api.assert_called_once_with('POST', 'system/execute_task/SEND_EMA')
    assert 'Task SEND_EMA executed.' in capsys.readouterr().out


def test_execute_task_menu_failure_prints_transcript(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={'SEND_EMA': 'Send EMA'})
    fake_interface.inputs_queue.put('1')
    fake_interface.api = MagicMock(side_effect=[
        (False, None),
        (True, {'transcript': [{'timestamp': 't1', 'message': 'oops'}]}),
    ])

    etm.execute_task_menu(fake_interface)

    fake_interface.api.assert_any_call('GET', 'system/get_transcript/15')
    out = capsys.readouterr().out
    assert 't1 - oops' in out
    assert 'Failed to execute task.' in out


def test_execute_task_menu_failure_no_transcript(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={'SEND_EMA': 'Send EMA'})
    fake_interface.inputs_queue.put('1')
    fake_interface.api = MagicMock(side_effect=[(False, None), (False, None)])

    etm.execute_task_menu(fake_interface)

    out = capsys.readouterr().out
    assert 'No transcript found or failed to retrieve.' in out
    assert 'Failed to execute task.' in out


def test_execute_task_menu_invalid_index(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={'SEND_EMA': 'Send EMA'})
    fake_interface.inputs_queue.put('99')

    etm.execute_task_menu(fake_interface)

    assert 'Invalid index.' in capsys.readouterr().out


# ------------------------------------------------------------
# execute_menu (outer wrapper wiring)
# ------------------------------------------------------------

def test_execute_menu_options_wired_correctly(fake_interface, monkeypatch):
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(etm, 'print_menu_options', mock_pmo)

    etm.execute_menu(fake_interface)

    menu_options = mock_pmo.call_args[0][1]
    assert menu_options['system']['menu_caller'] is etm.execute_task_menu
    assert menu_options['rscript']['menu_caller'] is etm.execute_r_script_menu


# ------------------------------------------------------------
# add_new_r_script_menu
# ------------------------------------------------------------

def test_add_new_r_script_menu_no_scripts_errors(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(return_value=(False, None))
    atm.add_new_r_script_menu(fake_interface)
    assert 'No R scripts available.' in capsys.readouterr().out


def test_add_new_r_script_menu_valid_time_success(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(side_effect=[
        (True, {'r_script_tasks': {'analyze': 'scripts/analyze'}}),
        (True, True),
    ])
    fake_interface.inputs_queue.put('1')
    fake_interface.inputs_queue.put('03:30:00')

    atm.add_new_r_script_menu(fake_interface)

    fake_interface.api.assert_any_call('POST', 'system/add_r_script_task/scripts/analyze.R/03:30:00')
    assert 'R script task scripts/analyze.R scheduled at 03:30:00.' in capsys.readouterr().out


def test_add_new_r_script_menu_blank_time_defaults(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(side_effect=[
        (True, {'r_script_tasks': {'analyze': 'scripts/analyze'}}),
        (True, True),
    ])
    fake_interface.inputs_queue.put('1')
    fake_interface.inputs_queue.put('')

    atm.add_new_r_script_menu(fake_interface)

    fake_interface.api.assert_any_call('POST', 'system/add_r_script_task/scripts/analyze.R/00:00:00')


def test_add_new_r_script_menu_invalid_time_defaults(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(side_effect=[
        (True, {'r_script_tasks': {'analyze': 'scripts/analyze'}}),
        (True, True),
    ])
    fake_interface.inputs_queue.put('1')
    fake_interface.inputs_queue.put('not-a-time')

    atm.add_new_r_script_menu(fake_interface)

    out = capsys.readouterr().out
    assert 'Invalid time format, using default 00:00:00.' in out
    fake_interface.api.assert_any_call('POST', 'system/add_r_script_task/scripts/analyze.R/00:00:00')


def test_add_new_r_script_menu_invalid_index(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(return_value=(True, {'r_script_tasks': {'analyze': 'scripts/analyze'}}))
    fake_interface.inputs_queue.put('99')

    atm.add_new_r_script_menu(fake_interface)

    assert 'Invalid index.' in capsys.readouterr().out


def test_add_new_r_script_menu_add_failure(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.api = MagicMock(side_effect=[
        (True, {'r_script_tasks': {'analyze': 'scripts/analyze'}}),
        (False, None),
    ])
    fake_interface.inputs_queue.put('1')
    fake_interface.inputs_queue.put('03:30:00')

    atm.add_new_r_script_menu(fake_interface)

    assert 'Failed to schedule R script task analyze.' in capsys.readouterr().out


# ------------------------------------------------------------
# add_new_task_menu
# ------------------------------------------------------------

def test_add_new_task_menu_no_task_types_errors(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={})
    atm.add_new_task_menu(fake_interface)
    assert 'No task types available.' in capsys.readouterr().out


def test_add_new_task_menu_run_r_script_delegates(fake_interface, monkeypatch):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={'RUN_R_SCRIPT': 'Run R Script'})
    fake_interface.inputs_queue.put('1')
    calls = []
    monkeypatch.setattr(atm, 'add_new_r_script_menu', lambda self: calls.append(self))

    atm.add_new_task_menu(fake_interface)

    assert calls == [fake_interface]


def test_add_new_task_menu_success(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={'SEND_EMA': 'Send EMA'})
    fake_interface.inputs_queue.put('1')
    fake_interface.inputs_queue.put('05:00:00')
    fake_interface.api = MagicMock(return_value=(True, True))

    atm.add_new_task_menu(fake_interface)

    fake_interface.api.assert_called_once_with('POST', 'system/add_system_task/SEND_EMA/05:00:00')
    assert 'Task added.' in capsys.readouterr().out


def test_add_new_task_menu_failure(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={'SEND_EMA': 'Send EMA'})
    fake_interface.inputs_queue.put('1')
    fake_interface.inputs_queue.put('05:00:00')
    fake_interface.api = MagicMock(return_value=(False, None))

    atm.add_new_task_menu(fake_interface)

    assert 'Failed to add task.' in capsys.readouterr().out


def test_add_new_task_menu_blank_time_defaults(fake_interface):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={'SEND_EMA': 'Send EMA'})
    fake_interface.inputs_queue.put('1')
    fake_interface.inputs_queue.put('')
    fake_interface.api = MagicMock(return_value=(True, True))

    atm.add_new_task_menu(fake_interface)

    fake_interface.api.assert_called_once_with('POST', 'system/add_system_task/SEND_EMA/00:00:00')


def test_add_new_task_menu_invalid_time_defaults(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={'SEND_EMA': 'Send EMA'})
    fake_interface.inputs_queue.put('1')
    fake_interface.inputs_queue.put('bogus')
    fake_interface.api = MagicMock(return_value=(True, True))

    atm.add_new_task_menu(fake_interface)

    out = capsys.readouterr().out
    assert 'Invalid time format, using default 00:00:00.' in out
    fake_interface.api.assert_called_once_with('POST', 'system/add_system_task/SEND_EMA/00:00:00')


def test_add_new_task_menu_invalid_index(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.get_task_types = MagicMock(return_value={'SEND_EMA': 'Send EMA'})
    fake_interface.inputs_queue.put('99')

    atm.add_new_task_menu(fake_interface)

    assert 'Invalid index.' in capsys.readouterr().out


# ------------------------------------------------------------
# add_task_menu (outer wrapper wiring)
# ------------------------------------------------------------

def test_add_task_menu_options_wired_correctly(fake_interface, monkeypatch):
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(atm, 'print_menu_options', mock_pmo)

    atm.add_task_menu(fake_interface)

    menu_options = mock_pmo.call_args[0][1]
    assert menu_options['system']['menu_caller'] is atm.add_new_task_menu
    assert menu_options['rscript']['menu_caller'] is atm.add_new_r_script_menu
