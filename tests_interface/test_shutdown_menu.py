"""Tests for _shutdown_menu.py."""
from unittest.mock import MagicMock

import requests

import user_interface_menus._shutdown_menu as _shutdown_menu


def test_shutdown_reports_already_down_when_uptime_unreachable(fake_interface, capsys):
    fake_interface.api = MagicMock(return_value=None)
    _shutdown_menu.shutdown_menu(fake_interface)
    out = capsys.readouterr().out
    assert "PRISM is already shut down." in out
    fake_interface.api.assert_called_once_with("GET", "system/uptime")


def test_shutdown_cancelled_on_no_confirmation(fake_interface, capsys):
    fake_interface.api = MagicMock(return_value={"uptime": "1h"})
    fake_interface.inputs_queue.put('n')
    _shutdown_menu.shutdown_menu(fake_interface)
    out = capsys.readouterr().out
    assert "Shutdown cancelled." in out
    fake_interface.api.assert_called_once_with("GET", "system/uptime")


def test_shutdown_confirmed_success(fake_interface, monkeypatch, capsys):
    fake_interface.api = MagicMock(return_value={"uptime": "1h"})
    fake_interface.inputs_queue.put('y')
    exit_calls = []
    monkeypatch.setattr('builtins.exit', lambda code=0: exit_calls.append(code))

    _shutdown_menu.shutdown_menu(fake_interface)

    out = capsys.readouterr().out
    assert "PRISM shut down." in out
    assert exit_calls == [0]
    assert fake_interface.api.call_args_list == [
        (("GET", "system/uptime"),),
        (("POST", "system/shutdown"),),
    ]


def test_shutdown_confirmed_connection_error_reports_already_down(fake_interface, monkeypatch, capsys):
    fake_interface.api = MagicMock(side_effect=[{"uptime": "1h"}, requests.ConnectionError()])
    fake_interface.inputs_queue.put('y')
    exit_calls = []
    monkeypatch.setattr('builtins.exit', lambda code=0: exit_calls.append(code))

    _shutdown_menu.shutdown_menu(fake_interface)

    out = capsys.readouterr().out
    assert "PRISM is already shut down." in out
    assert exit_calls == [0]


def test_shutdown_confirmed_generic_error_is_reported(fake_interface, monkeypatch, capsys):
    fake_interface.api = MagicMock(side_effect=[{"uptime": "1h"}, RuntimeError("server exploded")])
    fake_interface.inputs_queue.put('y')
    exit_calls = []
    monkeypatch.setattr('builtins.exit', lambda code=0: exit_calls.append(code))

    _shutdown_menu.shutdown_menu(fake_interface)

    out = capsys.readouterr().out
    assert "Error: server exploded" in out
    assert exit_calls == []
