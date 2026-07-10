"""Tests for check/_system_check_menu.py."""
import os
from unittest.mock import MagicMock

import pytest

import user_interface_menus.check._system_check_menu as _system_check_menu


@pytest.fixture(autouse=True)
def _no_real_terminal(monkeypatch):
    monkeypatch.setattr(os, 'system', lambda *a, **k: 0)


def test_diagnostics_success(fake_interface, capsys):
    fake_interface.api = MagicMock(return_value=(True, {"status": "ok"}))
    _system_check_menu.diagnostics(fake_interface)
    out = capsys.readouterr().out
    assert "System checks complete" in out
    fake_interface.api.assert_called_once_with("POST", "system/execute_task/CHECK_SYSTEM")


def test_diagnostics_failure_requests_transcript(fake_interface, capsys):
    fake_interface.api = MagicMock(return_value=(False, None))
    fake_interface.request_transcript = MagicMock()
    _system_check_menu.diagnostics(fake_interface)
    out = capsys.readouterr().out
    assert "Failure detected" in out
    fake_interface.request_transcript.assert_called_once_with(25, "get_transcript")


def test_system_check_menu_prints_status_and_breaks(fake_interface, monkeypatch, capsys):
    fake_interface.api = MagicMock(side_effect=[
        (True, {"uptime": "3 days"}),
        (True, {"mode": "LIVE"}),
    ])
    mock_print_menu_options = MagicMock(return_value=True)
    monkeypatch.setattr(_system_check_menu, 'print_menu_options', mock_print_menu_options)

    _system_check_menu.system_check_menu(fake_interface)

    out = capsys.readouterr().out
    assert "Mode: LIVE" in out
    assert "3 days" in out
    mock_print_menu_options.assert_called_once()
    args, kwargs = mock_print_menu_options.call_args
    assert set(args[1]) == {'diagnostics'}


def test_system_check_menu_errors_and_returns_when_api_unreachable(fake_interface, monkeypatch, capsys):
    fake_interface.api = MagicMock(return_value=(False, None))
    mock_print_menu_options = MagicMock(return_value=True)
    monkeypatch.setattr(_system_check_menu, 'print_menu_options', mock_print_menu_options)

    _system_check_menu.system_check_menu(fake_interface)

    out = capsys.readouterr().out
    assert "PRISM not running or inaccessible." in out
    mock_print_menu_options.assert_not_called()
