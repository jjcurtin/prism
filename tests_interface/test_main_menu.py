"""Tests for _main_menu.py.

main_menu() is a thin dispatcher: it builds the top-level menu_options dict
and hands off to menu_loop() with submenu=False. Because submenu=False,
menu_loop's own `while True` never breaks on its own (see
utils/_menu_navigation.py: `if print_menu_options(...) and submenu: break`
-- `and submenu` is always False here) -- the real top-level menu only ever
exits via the user picking 'exit' -> exit_interface() -> exit(0). Rather
than fight that intentional infinite loop, mock menu_loop itself (bound
directly in _main_menu's namespace via `from ..._menu_helper import *`) and
assert on what main_menu hands it -- that's the entirety of this module's
own responsibility.
"""
from unittest.mock import MagicMock

import user_interface_menus._main_menu as _main_menu


def test_main_menu_options_structure(fake_interface, monkeypatch):
    mock_menu_loop = MagicMock()
    monkeypatch.setattr(_main_menu, 'menu_loop', mock_menu_loop)

    _main_menu.main_menu(fake_interface)

    mock_menu_loop.assert_called_once()
    args, kwargs = mock_menu_loop.call_args
    self_arg, menu_options = args[0], args[1]
    assert self_arg is fake_interface
    assert set(menu_options) == {
        'command', 'check', 'tasks', 'participants',
        'logs', 'settings', 'shutdown', 'exit',
    }
    for key, option in menu_options.items():
        assert callable(option['menu_caller']), f"{key} menu_caller not callable"
        assert option['description']
    assert kwargs['submenu'] is False
    assert kwargs['additional_content'] is _main_menu.build_main_menu_status_panel


# ------------------------------------------------------------
# Main menu status panel (recent system tasks, send counts, start time)
# ------------------------------------------------------------

def _fake_api_for(transcript_entries=None, send_counts=None, start_time="2026-07-12 08:00:03"):
    transcript_entries = transcript_entries if transcript_entries is not None else []
    send_counts = send_counts if send_counts is not None else {
        'ema_on_study_sent': 3, 'ema_on_study_total': 10,
        'ema_all_sent': 3, 'ema_all_total': 12,
        'feedback_on_study_sent': 1, 'feedback_on_study_total': 10,
        'feedback_all_sent': 1, 'feedback_all_total': 12,
    }

    def fake_api(method, endpoint, **kwargs):
        if endpoint.startswith('system/get_transcript/'):
            return True, {'transcript': transcript_entries}
        if endpoint == 'participants/get_send_counts':
            return True, send_counts
        if endpoint == 'system/start_time':
            return True, {'start_time': start_time}
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    return fake_api


def test_recent_system_task_lines_parses_completion_lines(fake_interface):
    fake_interface.api = _fake_api_for(transcript_entries=[
        {'timestamp': '08:00:01', 'message': 'INFO - PRISM started in silent mode.'},
        {'timestamp': '09:00:00', 'message': 'INFO - CHECK_SYSTEM #482910 completed with status: SUCCESS.'},
        {'timestamp': '09:00:05', 'message': 'INFO - Processing SMS task: ema for participant 000000000'},
        {'timestamp': '10:00:00', 'message': 'INFO - RUN_R_SCRIPT #119284 completed with status: FAILURE.'},
    ])

    lines = _main_menu._recent_system_task_lines(fake_interface)

    assert any('CHECK_SYSTEM #482910' in line and 'SUCCESS' in line for line in lines)
    assert any('RUN_R_SCRIPT #119284' in line and 'FAILURE' in line for line in lines)
    assert not any('Processing SMS task' in line for line in lines)


def test_recent_system_task_lines_limits_to_five_most_recent(fake_interface):
    entries = [
        {'timestamp': f'0{i}:00:00', 'message': f'INFO - CHECK_SYSTEM #{i} completed with status: SUCCESS.'}
        for i in range(1, 8)
    ]
    fake_interface.api = _fake_api_for(transcript_entries=entries)

    lines = _main_menu._recent_system_task_lines(fake_interface)

    assert len(lines) == 5
    assert 'CHECK_SYSTEM #7' in lines[-1]
    assert not any('CHECK_SYSTEM #1 ' in line or line.endswith('#1') for line in lines)


def test_recent_system_task_lines_empty_when_no_matches(fake_interface):
    fake_interface.api = _fake_api_for(transcript_entries=[
        {'timestamp': '08:00:01', 'message': 'INFO - PRISM started in silent mode.'},
    ])

    lines = _main_menu._recent_system_task_lines(fake_interface)

    assert len(lines) == 1
    assert 'No recent system tasks found' in lines[0]


def test_send_count_lines_formats_on_study_and_all(fake_interface):
    fake_interface.api = _fake_api_for(send_counts={
        'ema_on_study_sent': 3, 'ema_on_study_total': 10,
        'ema_all_sent': 4, 'ema_all_total': 12,
        'feedback_on_study_sent': 1, 'feedback_on_study_total': 10,
        'feedback_all_sent': 2, 'feedback_all_total': 12,
    })

    lines = _main_menu._send_count_lines(fake_interface)

    assert any('EMA' in line and '3/10' in line and '4/12' in line for line in lines)
    assert any('Feedback' in line and '1/10' in line and '2/12' in line for line in lines)


def test_start_time_line_shows_server_start_timestamp(fake_interface):
    fake_interface.api = _fake_api_for(start_time="2026-07-12 08:00:03")

    line = _main_menu._start_time_line(fake_interface)

    assert '2026-07-12 08:00:03' in line


def test_start_time_line_handles_unreachable_server(fake_interface):
    fake_interface.api = MagicMock(return_value=(False, None))

    line = _main_menu._start_time_line(fake_interface)

    assert 'unavailable' in line


def test_build_main_menu_status_panel_uses_dash_sentinels(fake_interface):
    fake_interface.api = _fake_api_for()

    panel = _main_menu.build_main_menu_status_panel(fake_interface)

    assert panel.count('-') == 2
    assert any('Recent System Tasks' in line for line in panel)
