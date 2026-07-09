"""Tests for logs/_log_menu.py.

print_interface_log()/read_from_interface_log() use a hardcoded relative
path ("../logs/interface_logs/test_interface_log.txt") that assumes cwd is
the repo's src/ directory, per the pattern in test_menu_helper.py -- the
`fake_repo` fixture here fabricates that layout under tmp_path.
"""
import os
from unittest.mock import MagicMock

import pytest

import user_interface_menus._menu_helper as menu_helper
import user_interface_menus.logs._log_menu as _log_menu


@pytest.fixture(autouse=True)
def _no_real_terminal(monkeypatch):
    monkeypatch.setattr(os, 'system', lambda *a, **k: 0)
    monkeypatch.setattr(_log_menu, 'assistant_header_write', lambda *a, **k: None)


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (tmp_path / "logs" / "interface_logs").mkdir(parents=True)
    monkeypatch.chdir(src_dir)
    return tmp_path


# ------------------------------------------------------------
# log_menu loop
# ------------------------------------------------------------

def test_log_menu_options_structure(fake_interface, monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr(_log_menu, 'print_menu_options', mock)
    _log_menu.log_menu(fake_interface)
    mock.assert_called_once()
    args, kwargs = mock.call_args
    assert set(args[1]) == {'transcript', 'ema', 'feedback', 'interface'}
    assert kwargs['recommended_actions'] == ['transcript']


# ------------------------------------------------------------
# print_transcript
# ------------------------------------------------------------

def test_print_transcript_default_lines(fake_interface):
    fake_interface.request_transcript = MagicMock()
    _log_menu.print_transcript(fake_interface, 'get_transcript')
    fake_interface.request_transcript.assert_called_once_with('10', 'get_transcript')


def test_print_transcript_custom_lines(fake_interface):
    fake_interface.request_transcript = MagicMock()
    fake_interface.inputs_queue.put('25')
    _log_menu.print_transcript(fake_interface, 'get_ema_log')
    fake_interface.request_transcript.assert_called_once_with('25', 'get_ema_log')


def test_print_transcript_non_digit_falls_back_to_default(fake_interface):
    fake_interface.request_transcript = MagicMock()
    fake_interface.inputs_queue.put('abc')
    _log_menu.print_transcript(fake_interface, 'get_feedback_log')
    fake_interface.request_transcript.assert_called_once_with('10', 'get_feedback_log')


def test_print_transcript_skips_when_commands_queue_active(fake_interface):
    fake_interface.request_transcript = MagicMock()
    fake_interface.commands_queue.append('pending')
    _log_menu.print_transcript(fake_interface, 'get_transcript')
    fake_interface.request_transcript.assert_not_called()


# ------------------------------------------------------------
# print_interface_log
# ------------------------------------------------------------

def test_print_interface_log_missing_content_errors(fake_interface, monkeypatch, capsys):
    monkeypatch.setattr(menu_helper, 'read_from_interface_log', lambda: "")
    _log_menu.print_interface_log(fake_interface)
    assert "No content found in the interface log." in capsys.readouterr().out


def test_print_interface_log_file_not_found(fake_interface, monkeypatch, capsys):
    monkeypatch.setattr(menu_helper, 'read_from_interface_log', MagicMock(side_effect=FileNotFoundError()))
    _log_menu.print_interface_log(fake_interface)
    assert "Interface log file not found." in capsys.readouterr().out


def test_print_interface_log_prints_last_n_lines(fake_interface, fake_repo, capsys):
    menu_helper.write_to_interface_log("line1")
    menu_helper.write_to_interface_log("line2")
    menu_helper.write_to_interface_log("line3")
    fake_interface.inputs_queue.put('2')

    _log_menu.print_interface_log(fake_interface)

    out = capsys.readouterr().out
    assert "line2" in out
    assert "line3" in out
    assert "line1" not in out


def test_print_interface_log_skipped_when_commands_queue_active(fake_interface, fake_repo, capsys):
    menu_helper.write_to_interface_log("line1")
    fake_interface.commands_queue.append('pending')
    _log_menu.print_interface_log(fake_interface)
    assert capsys.readouterr().out == ""
