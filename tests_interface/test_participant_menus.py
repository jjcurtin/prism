"""Tests for user_interface_menus/participants/: _participant_management_menus.py,
_add_participant_menu.py, _individual_participant_menu.py.

Every menu function here talks to the server exclusively through `self.api(...)`
(see FakeInterface in conftest.py); tests replace `fake_interface.api` with a
MagicMock (return_value/side_effect) and assert on both the resulting menu
behavior and the exact call args passed to `self.api`.

Outer `while True: ... if print_menu_options(...): break` loops
(participant_management_menu, individual_participant_menu) are driven by
monkeypatching the target module's own `print_menu_options` name (bound via
`from user_interface_menus._menu_helper import *` at import time) to return
True immediately -- avoids the real interactive/terminal codepath entirely.
The same modules' `print_menu_header`/`assistant_header_write` are similarly
stubbed out where they're gated together with participant-list construction,
since real `assistant_header_write` does a typewriter effect requiring a real
terminal (get_cursor_position ANSI round trip) that would hang under pytest.

`write_to_interface_log` is neutralized repo-wide in this file (autouse)
because error()/success() call it with a hardcoded relative path
("../logs/interface_logs/...") that assumes cwd == src/; under pytest (cwd ==
repo root) that would attempt real file I/O outside the repo.
"""
from collections import deque
from unittest.mock import MagicMock, call

import pytest

import user_interface_menus._menu_helper as menu_helper
import user_interface_menus.participants._add_participant_menu as apm
import user_interface_menus.participants._individual_participant_menu as ipm
import user_interface_menus.participants._participant_management_menus as pmm
from user_interface_menus.utils._menu_navigation import ReturnToMainMenu


@pytest.fixture(autouse=True)
def _no_log_file(monkeypatch):
    monkeypatch.setattr(menu_helper, 'write_to_interface_log', lambda msg: None)


def _participant(unique_id, initials, subid, on_study=True):
    return {
        'unique_id': unique_id,
        'initials': initials,
        'subid': subid,
        'on_study': on_study,
    }


# ------------------------------------------------------------
# refresh_participants_menu
# ------------------------------------------------------------

def test_refresh_participants_menu_confirmed_success(fake_interface, capsys):
    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(True, {'ok': True}))
    pmm.refresh_participants_menu(fake_interface)
    out = capsys.readouterr().out
    assert 'Participants refreshed from CSV.' in out
    fake_interface.api.assert_called_once_with('POST', 'participants/refresh_participants')


def test_refresh_participants_menu_not_confirmed(fake_interface, capsys):
    fake_interface.inputs_queue.put('n')
    fake_interface.api = MagicMock(return_value=(True, {'ok': True}))
    pmm.refresh_participants_menu(fake_interface)
    out = capsys.readouterr().out
    assert 'Refresh cancelled.' in out
    fake_interface.api.assert_not_called()


def test_refresh_participants_menu_failure_reports_error_without_second_call(fake_interface, capsys):
    """Regression test for a fixed bug: _participant_management_menus.py's
    refresh_participants_menu used to call `self.api(...)` a SECOND time in
    its error-message f-string (a wasted duplicate network call) and chain
    `.get('status_code', 'Unknown')` onto the result -- a real failed/
    unreachable request (per PRISMInterface.api) returns None, not a dict,
    so `.get()` raised AttributeError before error() was ever invoked. Now
    calls self.api once and reports the failure without crashing.
    """
    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(False, None))
    pmm.refresh_participants_menu(fake_interface)
    assert fake_interface.api.call_count == 1
    assert 'Failed to refresh participants' in capsys.readouterr().out


# ------------------------------------------------------------
# send_announcement_menu
# ------------------------------------------------------------

def test_send_announcement_menu_on_study_only_formats_yes_in_url(fake_interface, monkeypatch, capsys):
    """Regression test for the earlier-this-session fix: require_on_study_param
    must be the literal string 'yes'/'no', not str(bool) ('True'/'False')."""
    fake_interface.inputs_queue.put('y')
    monkeypatch.setattr(pmm, 'print_twilio_terminal_prompt', lambda: 'hello participants')
    fake_interface.api = MagicMock(return_value=(True, {'sent': True}))

    pmm.send_announcement_menu(fake_interface)

    fake_interface.api.assert_called_once_with(
        'POST', 'participants/study_announcement/yes', json={'message': 'hello participants'}
    )
    assert 'Study announcement sent.' in capsys.readouterr().out


def test_send_announcement_menu_all_participants_formats_no_in_url(fake_interface, monkeypatch):
    fake_interface.inputs_queue.put('n')
    monkeypatch.setattr(pmm, 'print_twilio_terminal_prompt', lambda: 'hi all')
    fake_interface.api = MagicMock(return_value=(True, {'sent': True}))

    pmm.send_announcement_menu(fake_interface)

    fake_interface.api.assert_called_once_with(
        'POST', 'participants/study_announcement/no', json={'message': 'hi all'}
    )


def test_send_announcement_menu_empty_message_aborts_without_api_call(fake_interface, monkeypatch, capsys):
    fake_interface.inputs_queue.put('y')
    monkeypatch.setattr(pmm, 'print_twilio_terminal_prompt', lambda: '')
    fake_interface.api = MagicMock()

    pmm.send_announcement_menu(fake_interface)

    fake_interface.api.assert_not_called()
    assert 'Message cannot be empty' in capsys.readouterr().out


def test_send_announcement_menu_api_failure_reports_error(fake_interface, monkeypatch, capsys):
    fake_interface.inputs_queue.put('y')
    monkeypatch.setattr(pmm, 'print_twilio_terminal_prompt', lambda: 'hi')
    fake_interface.api = MagicMock(return_value=(False, None))

    pmm.send_announcement_menu(fake_interface)

    assert 'No participants found or failed to retrieve.' in capsys.readouterr().out


# ------------------------------------------------------------
# remove_participant_menu
# ------------------------------------------------------------

def test_remove_participant_menu_empty_id_errors(fake_interface, capsys):
    fake_interface.inputs_queue.put('')
    fake_interface.api = MagicMock()
    result = pmm.remove_participant_menu(fake_interface)
    assert result == 0
    assert 'Participant ID cannot be empty.' in capsys.readouterr().out
    fake_interface.api.assert_not_called()


def test_remove_participant_menu_confirmed_success(fake_interface, capsys):
    fake_interface.inputs_queue.put('123456789')
    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(True, True))
    result = pmm.remove_participant_menu(fake_interface)
    assert result == 1
    fake_interface.api.assert_called_once_with('DELETE', 'participants/remove_participant/123456789')
    assert 'Participant removed.' in capsys.readouterr().out


def test_remove_participant_menu_confirmed_failure(fake_interface, capsys):
    fake_interface.inputs_queue.put('123456789')
    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(False, None))
    result = pmm.remove_participant_menu(fake_interface)
    assert result == 0
    assert 'Failed to remove participant' in capsys.readouterr().out


def test_remove_participant_menu_not_confirmed_no_api_call(fake_interface):
    fake_interface.inputs_queue.put('123456789')
    fake_interface.inputs_queue.put('n')
    fake_interface.api = MagicMock()
    result = pmm.remove_participant_menu(fake_interface)
    assert result is None  # no else-branch on the "not confirmed" path
    fake_interface.api.assert_not_called()


# ------------------------------------------------------------
# access_specific_participant_menu
# ------------------------------------------------------------

def test_access_specific_participant_menu_empty_id_errors(fake_interface, capsys):
    fake_interface.inputs_queue.put('')
    fake_interface.api = MagicMock()
    result = pmm.access_specific_participant_menu(fake_interface)
    assert result == 0
    assert 'Participant ID cannot be empty.' in capsys.readouterr().out


def test_access_specific_participant_menu_found_delegates(fake_interface, monkeypatch):
    fake_interface.inputs_queue.put('123456789')
    fake_interface.api = MagicMock(return_value=(True, {'participant': {'unique_id': '123456789'}}))
    calls = []
    monkeypatch.setattr(pmm, 'individual_participant_menu', lambda self, pid: calls.append((self, pid)))

    pmm.access_specific_participant_menu(fake_interface)

    assert calls == [(fake_interface, '123456789')]
    fake_interface.api.assert_called_once_with('GET', 'participants/get_participant/123456789')


def test_access_specific_participant_menu_not_found_errors(fake_interface, capsys):
    fake_interface.inputs_queue.put('999')
    fake_interface.api = MagicMock(return_value=(False, None))
    result = pmm.access_specific_participant_menu(fake_interface)
    assert result == 0
    assert 'Unique ID not found' in capsys.readouterr().out


# ------------------------------------------------------------
# participant_management_menu
# ------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_terminal_header(monkeypatch):
    """participant_management_menu gates both header printing AND the
    participant-list menu_options construction on `not self.commands_queue`
    together -- can't decouple via commands_queue alone. Stub the
    header/typewriter calls directly instead so the real (terminal-driving)
    implementations never run, while leaving `self.commands_queue` falsy so
    the participant list still gets built."""
    monkeypatch.setattr(pmm, 'print_menu_header', lambda *a, **k: None)
    monkeypatch.setattr(pmm, 'assistant_header_write', lambda *a, **k: None)
    monkeypatch.setattr(ipm, 'print_menu_header', lambda *a, **k: None)
    monkeypatch.setattr(ipm, 'assistant_header_write', lambda *a, **k: None)


def test_participant_management_menu_static_options_wired_correctly(fake_interface, monkeypatch):
    fake_interface.api = MagicMock(return_value=(True, {'participants': []}))
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(pmm, 'print_menu_options', mock_pmo)

    pmm.participant_management_menu(fake_interface)

    menu_options = mock_pmo.call_args[0][1]
    assert menu_options['add']['menu_caller'] is apm.add_participant_menu
    assert menu_options['refresh']['menu_caller'] is pmm.refresh_participants_menu
    assert menu_options['announcement']['menu_caller'] is pmm.send_announcement_menu
    assert menu_options['remove']['menu_caller'] is pmm.remove_participant_menu
    assert menu_options['access']['menu_caller'] is pmm.access_specific_participant_menu
    assert 'sort' in menu_options and 'filter' in menu_options and 'schedule' in menu_options


def test_participant_management_menu_no_participants_sets_index_and_text_false(fake_interface, monkeypatch, capsys):
    fake_interface.api = MagicMock(return_value=(False, None))
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(pmm, 'print_menu_options', mock_pmo)

    pmm.participant_management_menu(fake_interface)

    assert mock_pmo.call_args.kwargs['index_and_text'] is False
    assert 'No participants found or failed to retrieve.' in capsys.readouterr().out


def test_participant_management_menu_default_sort_is_unique_id(fake_interface, monkeypatch):
    participants = [
        _participant('300', 'Charlie', 'Zed'),
        _participant('100', 'Alice', '3000'),
        _participant('200', 'Bob', 'Xavier'),
    ]
    fake_interface.api = MagicMock(return_value=(True, {'participants': participants}))
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(pmm, 'print_menu_options', mock_pmo)

    pmm.participant_management_menu(fake_interface)

    menu_options = mock_pmo.call_args[0][1]
    assert menu_options['1']['description'] == '3000 (Alice, 100)'
    assert menu_options['2']['description'] == 'Xavier (Bob, 200)'
    assert menu_options['3']['description'] == 'Zed (Charlie, 300)'
    assert fake_interface.participant_display_mode == 'unique_id'


def test_participant_management_menu_sort_by_name(fake_interface, monkeypatch):
    fake_interface.participant_display_mode = 'name'
    participants = [
        _participant('100', 'Zed', 'Adams'),
        _participant('200', 'Amy', 'Baker'),
    ]
    fake_interface.api = MagicMock(return_value=(True, {'participants': participants}))
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(pmm, 'print_menu_options', mock_pmo)

    pmm.participant_management_menu(fake_interface)

    menu_options = mock_pmo.call_args[0][1]
    assert menu_options['1']['description'] == 'Adams (Zed, 100)'
    assert menu_options['2']['description'] == 'Baker (Amy, 200)'


def test_participant_management_menu_sort_by_on_study(fake_interface, monkeypatch):
    fake_interface.participant_display_mode = 'on_study'
    participants = [
        _participant('300', 'C', 'C', on_study=False),
        _participant('100', 'A', 'A', on_study=True),
        _participant('200', 'B', 'B', on_study=False),
    ]
    fake_interface.api = MagicMock(return_value=(True, {'participants': participants}))
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(pmm, 'print_menu_options', mock_pmo)

    pmm.participant_management_menu(fake_interface)

    menu_options = mock_pmo.call_args[0][1]
    # on_study True participants first (sorted by unique_id), then False
    assert [menu_options[str(i)]['description'] for i in (1, 2, 3)] == [
        'A (A, 100)', 'B (B, 200)', 'C (C, 300)',
    ]


def test_participant_management_menu_filter_on_study_true(fake_interface, monkeypatch):
    fake_interface.participant_filter_settings = {'on_study': 'True'}
    participants = [
        _participant('100', 'A', 'A', on_study=True),
        _participant('200', 'B', 'B', on_study=False),
    ]
    fake_interface.api = MagicMock(return_value=(True, {'participants': participants}))
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(pmm, 'print_menu_options', mock_pmo)

    pmm.participant_management_menu(fake_interface)

    menu_options = mock_pmo.call_args[0][1]
    assert menu_options['1']['description'] == 'A (A, 100)'
    assert '2' not in menu_options


def test_participant_management_menu_filter_on_study_false(fake_interface, monkeypatch):
    fake_interface.participant_filter_settings = {'on_study': 'False'}
    participants = [
        _participant('100', 'A', 'A', on_study=True),
        _participant('200', 'B', 'B', on_study=False),
    ]
    fake_interface.api = MagicMock(return_value=(True, {'participants': participants}))
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(pmm, 'print_menu_options', mock_pmo)

    pmm.participant_management_menu(fake_interface)

    menu_options = mock_pmo.call_args[0][1]
    assert menu_options['1']['description'] == 'B (B, 200)'
    assert '2' not in menu_options


def test_participant_management_menu_numbered_lambda_uses_default_arg_capture(fake_interface, monkeypatch):
    """Confirms the `lambda self, participant_id = p['unique_id']: ...` idiom
    actually pins each option to its own participant (not late-bound to the
    last loop value)."""
    participants = [
        _participant('100', 'A', 'A'),
        _participant('200', 'B', 'B'),
    ]
    fake_interface.api = MagicMock(return_value=(True, {'participants': participants}))
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(pmm, 'print_menu_options', mock_pmo)

    pmm.participant_management_menu(fake_interface)

    menu_options = mock_pmo.call_args[0][1]
    calls = []
    monkeypatch.setattr(pmm, 'individual_participant_menu', lambda self, pid: calls.append(pid))
    menu_options['1']['menu_caller'](fake_interface)
    menu_options['2']['menu_caller'](fake_interface)
    assert calls == ['100', '200']


def test_participant_management_menu_exception_is_caught(fake_interface, monkeypatch, capsys):
    fake_interface.api = MagicMock(side_effect=RuntimeError('boom'))
    monkeypatch.setattr(pmm, 'print_menu_options', MagicMock(return_value=True))

    pmm.participant_management_menu(fake_interface)

    assert 'An error occurred in the participant management menu: boom' in capsys.readouterr().out


def test_participant_management_menu_propagates_return_to_main_menu(fake_interface, monkeypatch):
    """Contrast with test_participant_management_menu_exception_is_caught
    above: this menu is one of the few that wraps its whole dispatch loop
    in a try/except (most menu files don't), so it needs its own explicit
    `except ReturnToMainMenu: raise` carve-out ahead of the blanket `except
    Exception` -- otherwise "home" typed anywhere nested under participants/
    (e.g. from inside individual_participant_menu, reached via the 'access'
    option) would be caught here and swallowed into an "An error occurred
    in the participant management menu" message instead of unwinding all
    the way back to the main menu.
    """
    fake_interface.api = MagicMock(return_value=(True, {'participants': []}))
    monkeypatch.setattr(pmm, 'print_menu_options', MagicMock(side_effect=ReturnToMainMenu()))

    with pytest.raises(ReturnToMainMenu):
        pmm.participant_management_menu(fake_interface)


def _build_menu_options(fake_interface, monkeypatch, participants=None, filter_settings=None):
    fake_interface.api = MagicMock(return_value=(True, {'participants': participants or []}))
    if filter_settings is not None:
        fake_interface.participant_filter_settings = filter_settings
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(pmm, 'print_menu_options', mock_pmo)
    pmm.participant_management_menu(fake_interface)
    return mock_pmo.call_args[0][1]


def test_participant_management_menu_schedule_option_prints_schedule(fake_interface, monkeypatch, capsys):
    menu_options = _build_menu_options(fake_interface, monkeypatch)
    fake_interface.commands_queue = deque()
    fake_interface.api = MagicMock(return_value=(True, {
        'tasks': [{'participant_id': '100', 'task_type': 'ema', 'task_time': '16:00:00', 'on_study': True}]
    }))
    menu_options['schedule']['menu_caller'](fake_interface)
    out = capsys.readouterr().out
    assert 'Participant Task Schedule:' in out
    assert '100: ema at 16:00:00 - On Study: True' in out


def test_participant_management_menu_change_display_mode_valid(fake_interface, monkeypatch, capsys):
    menu_options = _build_menu_options(fake_interface, monkeypatch)
    fake_interface.inputs_queue.put('name')
    menu_options['sort']['menu_caller'](fake_interface)
    assert fake_interface.participant_display_mode == 'name'
    assert 'Display mode changed to name.' in capsys.readouterr().out


def test_participant_management_menu_change_display_mode_invalid(fake_interface, monkeypatch, capsys):
    menu_options = _build_menu_options(fake_interface, monkeypatch)
    original_mode = fake_interface.participant_display_mode
    fake_interface.inputs_queue.put('bogus')
    menu_options['sort']['menu_caller'](fake_interface)
    assert fake_interface.participant_display_mode == original_mode
    assert 'Invalid mode selected.' in capsys.readouterr().out


def test_participant_management_menu_filter_menu_updates_value(fake_interface, monkeypatch, capsys):
    menu_options = _build_menu_options(fake_interface, monkeypatch)
    fake_interface.inputs_queue.put('on_study')
    fake_interface.inputs_queue.put('False')
    menu_options['filter']['menu_caller'](fake_interface)
    assert fake_interface.participant_filter_settings['on_study'] == 'False'
    assert 'Filter on_study set to False.' in capsys.readouterr().out


def test_participant_management_menu_filter_menu_empty_choice_noop(fake_interface, monkeypatch):
    menu_options = _build_menu_options(fake_interface, monkeypatch)
    original = dict(fake_interface.participant_filter_settings)
    fake_interface.inputs_queue.put('')
    menu_options['filter']['menu_caller'](fake_interface)
    assert fake_interface.participant_filter_settings == original


def test_participant_management_menu_filter_menu_invalid_key(fake_interface, monkeypatch, capsys):
    menu_options = _build_menu_options(fake_interface, monkeypatch)
    fake_interface.inputs_queue.put('bogus_key')
    menu_options['filter']['menu_caller'](fake_interface)
    assert 'Invalid filter choice' in capsys.readouterr().out


def test_participant_management_menu_filter_menu_invalid_value(fake_interface, monkeypatch, capsys):
    menu_options = _build_menu_options(fake_interface, monkeypatch)
    fake_interface.inputs_queue.put('on_study')
    fake_interface.inputs_queue.put('maybe')
    menu_options['filter']['menu_caller'](fake_interface)
    assert "Invalid value. Please enter 'True', 'False', or 'All'." in capsys.readouterr().out


# ------------------------------------------------------------
# add_participant_menu
# ------------------------------------------------------------

def test_add_participant_menu_missing_initials_errors(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])  # skip header print
    fake_interface.inputs_queue.put('')
    apm.add_participant_menu(fake_interface)
    assert 'Initials are required.' in capsys.readouterr().out


def test_add_participant_menu_missing_subid_errors(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.inputs_queue.put('JD')
    fake_interface.inputs_queue.put('')
    apm.add_participant_menu(fake_interface)
    assert 'Sub ID is required' in capsys.readouterr().out


def test_add_participant_menu_non_numeric_subid_errors(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.inputs_queue.put('JD')
    fake_interface.inputs_queue.put('not-a-number')
    apm.add_participant_menu(fake_interface)
    out = capsys.readouterr().out
    assert 'Sub ID' in out and 'number' in out


def test_add_participant_menu_invalid_unique_id_generates_one(fake_interface, monkeypatch, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.inputs_queue.put('Alice')
    fake_interface.inputs_queue.put('3000')
    fake_interface.inputs_queue.put('bad-id')
    monkeypatch.setattr(apm.random, 'randint', lambda a, b: 111111111)
    fake_interface.inputs_queue.put('y')  # on_study
    fake_interface.inputs_queue.put('')  # phone number skip
    for _ in range(4):
        fake_interface.inputs_queue.put('')  # use defaults for all 4 time fields
    fake_interface.api = MagicMock(side_effect=[(False, None), (True, True)])  # no existing participants, then add succeeds

    apm.add_participant_menu(fake_interface)

    out = capsys.readouterr().out
    assert "Unique ID not valid. Generated: 111111111" in out
    payload = fake_interface.api.call_args_list[1].kwargs['json']
    assert payload['unique_id'] == '111111111'


def test_add_participant_menu_unique_id_collision_regenerates(fake_interface, monkeypatch, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.inputs_queue.put('Alice')
    fake_interface.inputs_queue.put('3000')
    fake_interface.inputs_queue.put('123456789')
    fake_interface.inputs_queue.put('y')
    fake_interface.inputs_queue.put('')
    for _ in range(4):
        fake_interface.inputs_queue.put('')
    monkeypatch.setattr(apm.random, 'randint', lambda a, b: 222222222)
    fake_interface.api = MagicMock(side_effect=[
        (True, {'participants': [{'unique_id': '123456789'}]}),
        (True, True),
    ])

    apm.add_participant_menu(fake_interface)

    out = capsys.readouterr().out
    assert "already exists. Generated a new one: 222222222" in out
    payload = fake_interface.api.call_args_list[1].kwargs['json']
    assert payload['unique_id'] == '222222222'


def test_add_participant_menu_default_times_used_when_blank(fake_interface):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.inputs_queue.put('Alice')
    fake_interface.inputs_queue.put('3000')
    fake_interface.inputs_queue.put('123456789')
    fake_interface.inputs_queue.put('y')
    fake_interface.inputs_queue.put('5551234')
    for _ in range(4):
        fake_interface.inputs_queue.put('')
    fake_interface.api = MagicMock(side_effect=[(False, None), (True, True)])

    apm.add_participant_menu(fake_interface)

    payload = fake_interface.api.call_args_list[1].kwargs['json']
    assert payload['ema_time'] == '16:00:00'
    assert payload['ema_reminder_time'] == '19:00:00'
    assert payload['feedback_time'] == '07:00:00'
    assert payload['feedback_reminder_time'] == '12:00:00'
    assert payload['initials'] == 'Alice'
    assert payload['subid'] == '3000'
    assert payload['on_study'] is True
    assert payload['phone_number'] == '5551234'


def test_add_participant_menu_invalid_time_format_falls_back_to_default(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.inputs_queue.put('Alice')
    fake_interface.inputs_queue.put('3000')
    fake_interface.inputs_queue.put('123456789')
    fake_interface.inputs_queue.put('y')
    fake_interface.inputs_queue.put('')
    fake_interface.inputs_queue.put('not-a-time')
    for _ in range(3):
        fake_interface.inputs_queue.put('')
    fake_interface.api = MagicMock(side_effect=[(False, None), (True, True)])

    apm.add_participant_menu(fake_interface)

    out = capsys.readouterr().out
    assert 'Invalid time format for not-a-time' in out
    payload = fake_interface.api.call_args_list[1].kwargs['json']
    assert payload['ema_time'] == '16:00:00'


def test_add_participant_menu_success_and_failure(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.inputs_queue.put('Alice')
    fake_interface.inputs_queue.put('3000')
    fake_interface.inputs_queue.put('123456789')
    fake_interface.inputs_queue.put('y')
    fake_interface.inputs_queue.put('')
    for _ in range(4):
        fake_interface.inputs_queue.put('')
    fake_interface.api = MagicMock(side_effect=[(False, None), (True, True)])
    apm.add_participant_menu(fake_interface)
    assert 'Participant added.' in capsys.readouterr().out


def test_add_participant_menu_add_api_failure(fake_interface, capsys):
    fake_interface.commands_queue = deque(['x'])
    fake_interface.inputs_queue.put('Alice')
    fake_interface.inputs_queue.put('3000')
    fake_interface.inputs_queue.put('123456789')
    fake_interface.inputs_queue.put('y')
    fake_interface.inputs_queue.put('')
    for _ in range(4):
        fake_interface.inputs_queue.put('')
    fake_interface.api = MagicMock(side_effect=[(False, None), (False, None)])
    apm.add_participant_menu(fake_interface)
    assert 'Failed to add participant.' in capsys.readouterr().out


# ------------------------------------------------------------
# individual_participant_menu
# ------------------------------------------------------------

def test_individual_participant_menu_not_found_errors(fake_interface, capsys):
    fake_interface.api = MagicMock(return_value=(False, None))
    ipm.individual_participant_menu(fake_interface, '123456789')
    assert 'Failed to retrieve participant schedule.' in capsys.readouterr().out


def test_individual_participant_menu_missing_participant_key_errors(fake_interface, capsys):
    fake_interface.api = MagicMock(return_value=(True, {'participant': None}))
    ipm.individual_participant_menu(fake_interface, '123456789')
    assert 'Failed to retrieve participant schedule.' in capsys.readouterr().out


def _open_individual_menu(fake_interface, monkeypatch, participant):
    fake_interface.api = MagicMock(return_value=(True, {'participant': participant}))
    mock_pmo = MagicMock(return_value=True)
    monkeypatch.setattr(ipm, 'print_menu_options', mock_pmo)
    ipm.individual_participant_menu(fake_interface, participant['unique_id'])
    return mock_pmo.call_args[0][1]


def test_individual_participant_menu_builds_field_options(fake_interface, monkeypatch):
    participant = {
        'unique_id': '123456789', 'initials': 'Alice', 'subid': '3000',
        'on_study': True, 'phone_number': '555', 'ema_time': '16:00:00',
        'ema_reminder_time': '19:00:00', 'feedback_time': '07:00:00',
        'feedback_reminder_time': '12:00:00',
    }
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)
    assert menu_options['1']['description'] == 'initials: Alice'
    assert menu_options['4']['description'] == 'on_study: True'
    assert set(menu_options.keys()) >= {'1', '2', '3', '4', '5', '6', '7', '8', '9', 'remove', 'ema', 'feedback', 'message'}


def test_individual_participant_menu_update_field_text_success(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': True,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('Alicia')
    fake_interface.api = MagicMock(return_value=(True, True))
    menu_options['1']['menu_caller'](fake_interface)

    fake_interface.api.assert_called_once_with('PUT', 'participants/update_participant/1/initials/Alicia')
    assert 'Participant updated.' in capsys.readouterr().out


def test_individual_participant_menu_update_field_failure(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': True,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('Alicia')
    fake_interface.api = MagicMock(return_value=(False, None))
    menu_options['1']['menu_caller'](fake_interface)

    assert 'Failed to update participant.' in capsys.readouterr().out


def test_individual_participant_menu_update_subid_valid(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': True,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('4000')
    fake_interface.api = MagicMock(return_value=(True, True))
    menu_options['2']['menu_caller'](fake_interface)

    fake_interface.api.assert_called_once_with('PUT', 'participants/update_participant/1/subid/4000')
    assert 'Participant updated.' in capsys.readouterr().out


def test_individual_participant_menu_update_subid_non_numeric_rejected(fake_interface, monkeypatch, capsys):
    """Regression test: subid must be numeric (per explicit request), same
    validation applied on update as on add.
    """
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': True,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('not-a-number')
    fake_interface.api = MagicMock()
    menu_options['2']['menu_caller'](fake_interface)

    fake_interface.api.assert_not_called()
    assert 'Sub ID must be a number' in capsys.readouterr().out


def test_individual_participant_menu_update_on_study_true(fake_interface, monkeypatch):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('true')
    fake_interface.api = MagicMock(return_value=(True, True))
    menu_options['4']['menu_caller'](fake_interface)

    fake_interface.api.assert_called_once_with('PUT', 'participants/update_participant/1/on_study/True')
    assert participant['on_study'] == 'True'


def test_individual_participant_menu_update_on_study_invalid(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('maybe')
    fake_interface.api = MagicMock()
    menu_options['4']['menu_caller'](fake_interface)

    fake_interface.api.assert_not_called()
    assert "Invalid input for on_study" in capsys.readouterr().out


def test_individual_participant_menu_update_time_field_invalid_format(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('not-a-time')
    fake_interface.api = MagicMock()
    menu_options['6']['menu_caller'](fake_interface)

    fake_interface.api.assert_not_called()
    assert 'Invalid time format for ema_time' in capsys.readouterr().out


def test_individual_participant_menu_send_ema_survey_confirmed_success(fake_interface, monkeypatch, capsys):
    """Regression test: an off-study participant still gets sent the real,
    personalized survey -- process_task's recurring-task off-study skip
    doesn't apply to this one-time path -- but only behind an extra
    confirmation naming that fact specifically, replacing (not stacking on
    top of) the generic confirmation.
    """
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(True, True))
    menu_options['ema']['menu_caller'](fake_interface)

    fake_interface.api.assert_called_once_with('POST', 'participants/send_survey/1/ema')
    out = capsys.readouterr().out
    assert 'Participant is not on study. Send ema survey anyway?' in out
    assert 'Ema survey sent.' in out


def test_individual_participant_menu_send_ema_survey_on_study_uses_generic_prompt(fake_interface, monkeypatch, capsys):
    """An on-study participant keeps the original generic confirmation --
    the off-study-specific prompt replaces it only when actually off study."""
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': True,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(True, True))
    menu_options['ema']['menu_caller'](fake_interface)

    fake_interface.api.assert_called_once_with('POST', 'participants/send_survey/1/ema')
    out = capsys.readouterr().out
    assert 'Send a one-time ema survey now?' in out
    assert 'not on study' not in out


def test_individual_participant_menu_send_ema_survey_off_study_as_string_still_warns(fake_interface, monkeypatch, capsys):
    """Regression test: on_study is a real bool when freshly fetched from
    the API, but update_field_menu stores a live edit back as the string
    "False" instead (see test_individual_participant_menu_update_on_study_true).
    The off-study warning must still trigger for that string form, not
    just the bool -- an RA toggling on_study off and then immediately
    sending a one-time survey in the same session is exactly the scenario
    this covers.
    """
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': 'False',
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(True, True))
    menu_options['ema']['menu_caller'](fake_interface)

    fake_interface.api.assert_called_once_with('POST', 'participants/send_survey/1/ema')
    assert 'Participant is not on study. Send ema survey anyway?' in capsys.readouterr().out


def test_individual_participant_menu_send_ema_survey_confirmed_failure(fake_interface, monkeypatch, capsys):
    """The route now sends synchronously and reports the real outcome, so a
    502 from the backend must surface here as a failure, not an optimistic
    success."""
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(False, None))
    menu_options['ema']['menu_caller'](fake_interface)

    fake_interface.api.assert_called_once_with('POST', 'participants/send_survey/1/ema')
    assert 'Failed to send ema survey.' in capsys.readouterr().out


def test_individual_participant_menu_send_ema_survey_not_confirmed_no_api_call(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('n')
    fake_interface.api = MagicMock()
    menu_options['ema']['menu_caller'](fake_interface)

    fake_interface.api.assert_not_called()


def test_individual_participant_menu_send_feedback_survey_confirmed_success(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(True, True))
    menu_options['feedback']['menu_caller'](fake_interface)

    fake_interface.api.assert_called_once_with('POST', 'participants/send_survey/1/feedback')
    out = capsys.readouterr().out
    assert 'Participant is not on study. Send feedback survey anyway?' in out
    assert 'Feedback survey sent.' in out


def test_individual_participant_menu_send_feedback_survey_not_confirmed_no_api_call(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('n')
    fake_interface.api = MagicMock()
    menu_options['feedback']['menu_caller'](fake_interface)

    fake_interface.api.assert_not_called()


def test_individual_participant_menu_send_message_success(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    monkeypatch.setattr(ipm, 'print_twilio_terminal_prompt', lambda: 'hello there')
    fake_interface.api = MagicMock(return_value=(True, True))
    menu_options['message']['menu_caller'](fake_interface)

    fake_interface.api.assert_called_once_with('POST', 'participants/send_custom_sms/1', json={'message': 'hello there'})
    assert 'Message sent.' in capsys.readouterr().out


def test_individual_participant_menu_send_message_empty_errors(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    monkeypatch.setattr(ipm, 'print_twilio_terminal_prompt', lambda: '')
    fake_interface.api = MagicMock()
    menu_options['message']['menu_caller'](fake_interface)

    fake_interface.api.assert_not_called()
    assert 'Message cannot be empty.' in capsys.readouterr().out


def test_individual_participant_menu_remove_confirmed_success(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(True, True))
    result = menu_options['remove']['menu_caller'](fake_interface)

    fake_interface.api.assert_called_once_with('DELETE', 'participants/remove_participant/1')
    assert result == 1
    assert 'Participant removed.' in capsys.readouterr().out


def test_individual_participant_menu_remove_confirmed_failure(fake_interface, monkeypatch, capsys):
    participant = {'unique_id': '1', 'initials': 'Alice', 'subid': '3000', 'on_study': False,
                    'phone_number': '555', 'ema_time': '16:00:00', 'ema_reminder_time': '19:00:00',
                    'feedback_time': '07:00:00', 'feedback_reminder_time': '12:00:00'}
    menu_options = _open_individual_menu(fake_interface, monkeypatch, participant)

    fake_interface.inputs_queue.put('y')
    fake_interface.api = MagicMock(return_value=(False, None))
    result = menu_options['remove']['menu_caller'](fake_interface)

    assert result == 0
    assert 'Failed to remove participant.' in capsys.readouterr().out
