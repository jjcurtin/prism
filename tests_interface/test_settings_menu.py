"""Tests for settings/_settings_menu.py.

Setter functions (set_window_width, set_related_options_threshold, etc.) are
mocked at the point of use here -- they're bound directly into this module's
namespace via `from ..._menu_helper import *`, and their real global-mutating
+ file-writing behavior is already covered by tests_interface/test_menu_helper.py.
These tests only check _settings_menu.py's own responsibility: reading
input, validating/converting it, and calling the right setter (or not).
"""
import os
from unittest.mock import MagicMock

import pytest

import user_interface_menus._menu_helper as menu_helper
import user_interface_menus.settings._settings_menu as _settings_menu


@pytest.fixture(autouse=True)
def _no_real_terminal(monkeypatch):
    monkeypatch.setattr(os, 'system', lambda *a, **k: 0)
    monkeypatch.setattr(_settings_menu, 'assistant_header_write', lambda *a, **k: None)


# ------------------------------------------------------------
# window_width_settings / window_height_settings
# ------------------------------------------------------------

def test_window_width_settings_valid(fake_interface, monkeypatch):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_window_width', mock_set)
    fake_interface.inputs_queue.put('100')
    _settings_menu.window_width_settings(fake_interface)
    mock_set.assert_called_once_with(100)


def test_window_width_settings_non_digit(fake_interface, monkeypatch, capsys):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_window_width', mock_set)
    fake_interface.inputs_queue.put('abc')
    result = _settings_menu.window_width_settings(fake_interface)
    assert result == 0
    mock_set.assert_not_called()
    assert "must be an integer" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["79", "201"])
def test_window_width_settings_out_of_range(fake_interface, monkeypatch, capsys, value):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_window_width', mock_set)
    fake_interface.inputs_queue.put(value)
    result = _settings_menu.window_width_settings(fake_interface)
    assert result == 0
    mock_set.assert_not_called()
    assert "cannot exceed 200" in capsys.readouterr().out


def test_window_height_settings_valid(fake_interface, monkeypatch):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_window_height', mock_set)
    fake_interface.inputs_queue.put('10')
    _settings_menu.window_height_settings(fake_interface)
    mock_set.assert_called_once_with(10)


@pytest.mark.parametrize("value", ["4", "16"])
def test_window_height_settings_out_of_range(fake_interface, monkeypatch, capsys, value):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_window_height', mock_set)
    fake_interface.inputs_queue.put(value)
    result = _settings_menu.window_height_settings(fake_interface)
    assert result == 0
    mock_set.assert_not_called()
    assert "between 5 and 15" in capsys.readouterr().out


def test_window_height_settings_non_digit(fake_interface, monkeypatch, capsys):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_window_height', mock_set)
    fake_interface.inputs_queue.put('x')
    _settings_menu.window_height_settings(fake_interface)
    mock_set.assert_not_called()
    assert "must be an integer" in capsys.readouterr().out


# ------------------------------------------------------------
# print_display_params
# ------------------------------------------------------------

def test_print_display_params_prints_current_values(fake_interface, monkeypatch, capsys):
    monkeypatch.setattr(menu_helper.ui_state, 'window_width', 155)
    monkeypatch.setattr(menu_helper.ui_state, 'right_align', True)
    monkeypatch.setattr(menu_helper.ui_state, 'color_on', False)
    _settings_menu.print_display_params(fake_interface)
    out = capsys.readouterr().out
    assert "PRISM window width: 155" in out
    assert "enabled" in out
    assert "disabled" in out


def test_print_display_params_skipped_when_commands_queue_active(fake_interface, capsys):
    fake_interface.commands_queue.append('pending')
    _settings_menu.print_display_params(fake_interface)
    assert capsys.readouterr().out == ""


# ------------------------------------------------------------
# display_settings loop
# ------------------------------------------------------------

def test_display_settings_options_structure(fake_interface, monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr(_settings_menu, 'print_menu_options', mock)
    _settings_menu.display_settings(fake_interface)
    mock.assert_called_once()
    args, kwargs = mock.call_args
    assert set(args[1]) == {'print', 'width', 'height', 'align', 'color'}


# ------------------------------------------------------------
# related_parameter / best_related_parameter
# (identical 0.0-1.0 float threshold validation pattern)
# ------------------------------------------------------------

_THRESHOLD_FUNCS = [
    ("related_parameter", "set_related_options_threshold"),
    ("best_related_parameter", "set_best_options_threshold"),
]


@pytest.mark.parametrize("func_name,setter_name", _THRESHOLD_FUNCS)
def test_threshold_style_parameter_valid(fake_interface, monkeypatch, func_name, setter_name):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, setter_name, mock_set)
    fake_interface.inputs_queue.put('0.5')
    getattr(_settings_menu, func_name)(fake_interface)
    mock_set.assert_called_once_with(0.5)


@pytest.mark.parametrize("func_name,setter_name", _THRESHOLD_FUNCS)
def test_threshold_style_parameter_empty_input_noop(fake_interface, monkeypatch, func_name, setter_name):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, setter_name, mock_set)
    fake_interface.inputs_queue.put('')
    result = getattr(_settings_menu, func_name)(fake_interface)
    assert result == 0
    mock_set.assert_not_called()


@pytest.mark.parametrize("func_name,setter_name", _THRESHOLD_FUNCS)
@pytest.mark.parametrize("value", ["1.5", "-0.1"])
def test_threshold_style_parameter_out_of_range(fake_interface, monkeypatch, func_name, setter_name, value):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, setter_name, mock_set)
    fake_interface.inputs_queue.put(value)
    result = getattr(_settings_menu, func_name)(fake_interface)
    assert result == 0
    mock_set.assert_not_called()


@pytest.mark.parametrize("func_name,setter_name", _THRESHOLD_FUNCS)
def test_threshold_style_parameter_non_numeric_is_handled_cleanly(fake_interface, monkeypatch, func_name, setter_name):
    """Unlike param_set_type_speed (see bug tests below), these two
    correctly `return 0` inside their except block, so non-numeric input
    is handled without raising."""
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, setter_name, mock_set)
    fake_interface.inputs_queue.put('notanumber')
    result = getattr(_settings_menu, func_name)(fake_interface)
    assert result == 0
    mock_set.assert_not_called()


# ------------------------------------------------------------
# menu_delay_parameter / timeout_parameter
# ------------------------------------------------------------

def test_menu_delay_parameter_valid(fake_interface, monkeypatch):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_menu_delay', mock_set)
    fake_interface.inputs_queue.put('1.5')
    _settings_menu.menu_delay_parameter(fake_interface)
    mock_set.assert_called_once_with(1.5)


def test_menu_delay_parameter_non_positive(fake_interface, monkeypatch, capsys):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_menu_delay', mock_set)
    fake_interface.inputs_queue.put('0')
    result = _settings_menu.menu_delay_parameter(fake_interface)
    assert result == 0
    mock_set.assert_not_called()
    assert "positive number" in capsys.readouterr().out


def test_timeout_parameter_valid(fake_interface, monkeypatch):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_timeout', mock_set)
    fake_interface.inputs_queue.put('30')
    _settings_menu.timeout_parameter(fake_interface)
    mock_set.assert_called_once_with(30)


def test_timeout_parameter_non_positive(fake_interface, monkeypatch, capsys):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_timeout', mock_set)
    fake_interface.inputs_queue.put('-5')
    result = _settings_menu.timeout_parameter(fake_interface)
    assert result == 0
    mock_set.assert_not_called()
    assert "positive integer" in capsys.readouterr().out


# ------------------------------------------------------------
# param_set_type_speed
# ------------------------------------------------------------

def test_param_set_type_speed_valid(fake_interface, monkeypatch):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_assistant_type_speed', mock_set)
    fake_interface.inputs_queue.put('0.02')
    _settings_menu.param_set_type_speed(fake_interface)
    mock_set.assert_called_once_with(0.02)


def test_param_set_type_speed_empty_input_noop(fake_interface, monkeypatch):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_assistant_type_speed', mock_set)
    fake_interface.inputs_queue.put('')
    result = _settings_menu.param_set_type_speed(fake_interface)
    assert result == 0
    mock_set.assert_not_called()


def test_param_set_type_speed_out_of_range(fake_interface, monkeypatch, capsys):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_assistant_type_speed', mock_set)
    fake_interface.inputs_queue.put('0.1')
    result = _settings_menu.param_set_type_speed(fake_interface)
    assert result == 0
    mock_set.assert_not_called()
    assert "between 0.001 and 0.03" in capsys.readouterr().out


def test_param_set_type_speed_non_numeric_returns_without_raising(fake_interface, monkeypatch, capsys):
    """Regression test for a fixed bug: settings/_settings_menu.py's
    param_set_type_speed `except Exception:` branch used to print "Invalid
    input..." but not `return`, so execution fell through to
    `set_assistant_type_speed(float(new_speed))` OUTSIDE the try/except,
    which re-raised the same ValueError uncaught. Non-numeric input now
    returns cleanly after reporting the error.
    """
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_assistant_type_speed', mock_set)
    fake_interface.inputs_queue.put('notanumber')
    result = _settings_menu.param_set_type_speed(fake_interface)
    assert result == 0
    mock_set.assert_not_called()
    assert 'Invalid input' in capsys.readouterr().out


# ------------------------------------------------------------
# print_params / parameter_settings loop
# ------------------------------------------------------------

def test_print_params_prints_all_values(fake_interface, capsys):
    _settings_menu.print_params(fake_interface)
    out = capsys.readouterr().out
    assert "RELATED_OPTIONS_THRESHOLD" in out
    assert "ASSISTANT_TYPE_SPEED" in out
    assert "TIMEOUT" in out


def test_print_params_skipped_when_commands_queue_active(fake_interface, capsys):
    fake_interface.commands_queue.append('pending')
    _settings_menu.print_params(fake_interface)
    assert capsys.readouterr().out == ""


def test_parameter_settings_options_structure(fake_interface, monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr(_settings_menu, 'print_menu_options', mock)
    _settings_menu.parameter_settings(fake_interface)
    mock.assert_called_once()
    args, kwargs = mock.call_args
    assert set(args[1]) == {
        'print', 'threshold', 'best threshold',
        'type speed', 'delay', 'timeout',
    }


# ------------------------------------------------------------
# readme
# ------------------------------------------------------------

def test_readme_enable(fake_interface, monkeypatch, capsys):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_show_readme', mock_set)
    fake_interface.inputs_queue.put('y')
    _settings_menu.readme(fake_interface)
    mock_set.assert_called_once_with(True)
    assert "enabled" in capsys.readouterr().out


def test_readme_disable(fake_interface, monkeypatch, capsys):
    mock_set = MagicMock()
    monkeypatch.setattr(_settings_menu, 'set_show_readme', mock_set)
    fake_interface.inputs_queue.put('n')
    _settings_menu.readme(fake_interface)
    mock_set.assert_called_once_with(False)
    assert "disabled" in capsys.readouterr().out


# ------------------------------------------------------------
# system_settings / settings_menu loops
# ------------------------------------------------------------

def test_system_settings_options_structure(fake_interface, monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr(_settings_menu, 'print_menu_options', mock)
    _settings_menu.system_settings(fake_interface)
    mock.assert_called_once()
    args, kwargs = mock.call_args
    assert set(args[1]) == {'params', 'readme set'}


def test_settings_menu_options_structure(fake_interface, monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr(_settings_menu, 'print_menu_options', mock)
    _settings_menu.settings_menu(fake_interface)
    mock.assert_called_once()
    args, kwargs = mock.call_args
    assert set(args[1]) == {'system', 'display'}
