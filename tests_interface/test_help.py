"""Tests for help/_help_menu.py, help/_developer_documentation.py, and
help/_research_assistant_documentation.py.

These are mostly static-content menus (infopage() calls with hardcoded
text), so coverage here is intentionally light: confirm menu structures,
confirm a representative sample of the content renders without raising, and
document one real bug found along the way (see
test_research_assistant_documentation_navigation_advanced_missing_self_param).
"""
import os
from unittest.mock import MagicMock

import pytest

import user_interface_menus.help._developer_documentation as _developer_documentation
import user_interface_menus.help._help_menu as _help_menu
import user_interface_menus.help._research_assistant_documentation as _research_assistant_documentation


@pytest.fixture(autouse=True)
def _no_real_terminal(monkeypatch):
    monkeypatch.setattr(os, 'system', lambda *a, **k: 0)


# ------------------------------------------------------------
# help_menu / read_me / general_information
# ------------------------------------------------------------

def test_help_menu_options_structure(fake_interface, monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr(_help_menu, 'print_menu_options', mock)
    monkeypatch.setattr(_help_menu, 'assistant_header_write', lambda *a, **k: None)

    _help_menu.help_menu(fake_interface)

    mock.assert_called_once()
    args, kwargs = mock.call_args
    assert set(args[1]) == {'readme', 'general', 'ra', 'dev'}
    assert kwargs['recommended_actions'] == ['readme', 'ra']


def test_read_me_prints_lines(fake_interface, capsys):
    _help_menu.read_me(fake_interface)
    out = capsys.readouterr().out
    assert "command" in out


def test_read_me_skipped_when_commands_queue_active(fake_interface, capsys):
    fake_interface.commands_queue.append('pending')
    _help_menu.read_me(fake_interface)
    assert capsys.readouterr().out == ""


def test_general_information_prints_summary(fake_interface, capsys):
    _help_menu.general_information(fake_interface)
    out = capsys.readouterr().out
    assert "manage and monitor participants" in out


# ------------------------------------------------------------
# developer_documentation
# ------------------------------------------------------------

def test_developer_documentation_top_level_structure(fake_interface, monkeypatch):
    captured = {}

    def capture(self, menu_options, submenu=True, recommended_actions=None, **kw):
        captured['menu_options'] = menu_options
        captured['recommended_actions'] = recommended_actions
        return True

    monkeypatch.setattr(_developer_documentation, 'print_menu_options', capture)
    _developer_documentation.developer_documentation(fake_interface)

    top_level = captured['menu_options']
    assert set(top_level) == {'start', 'architecture', 'backend', 'server', 'ui', 'qualtrics'}
    for key, option in top_level.items():
        assert callable(option['menu_caller']), f"{key} menu_caller not callable"
    assert captured['recommended_actions'] == ['start']


def test_developer_documentation_leaf_infopages_render(fake_interface, monkeypatch, capsys):
    captured = {}

    def capture(self, menu_options, submenu=True, recommended_actions=None, **kw):
        captured['menu_options'] = menu_options
        return True

    monkeypatch.setattr(_developer_documentation, 'print_menu_options', capture)
    _developer_documentation.developer_documentation(fake_interface)
    top_level = captured['menu_options']

    # architecture_overview and prism_user_interface_documentation are plain
    # infopages (no nested submenu) -- exercise them directly, unmocked.
    top_level['architecture']['menu_caller'](fake_interface)
    assert "many components" in capsys.readouterr().out

    top_level['ui']['menu_caller'](fake_interface)
    assert "prism_interface.py" in capsys.readouterr().out


def test_developer_documentation_nested_submenus_run_without_raising(fake_interface, monkeypatch):
    captured = {}

    def capture(self, menu_options, submenu=True, recommended_actions=None, **kw):
        captured['menu_options'] = menu_options
        return True

    monkeypatch.setattr(_developer_documentation, 'print_menu_options', capture)
    _developer_documentation.developer_documentation(fake_interface)
    top_level = captured['menu_options']

    # nested submenus (backend/server) resolve print_menu_options via the
    # same module global, so the mock above breaks their inner loops too.
    top_level['backend']['menu_caller'](fake_interface)
    assert set(captured['menu_options']) == {
        'task_abstraction', 'task_managers', 'check_system', 'data_management'
    }

    top_level['server']['menu_caller'](fake_interface)
    assert set(captured['menu_options']) == {
        'system_endpoints', 'participant_endpoints', 'qualtrics_endpoints'
    }


# ------------------------------------------------------------
# research_assistant_documentation
# ------------------------------------------------------------

def test_research_assistant_documentation_top_level_structure(fake_interface, monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr(_research_assistant_documentation, 'print_menu_options', mock)

    _research_assistant_documentation.research_assistant_documentation(fake_interface)

    mock.assert_called_once()
    args, kwargs = mock.call_args
    assert set(args[1]) == {
        'start', 'navigation', 'navigation advanced', 'terminals',
        'task management', 'participant management',
    }
    assert kwargs['recommended_actions'] == ['start', 'tasks', 'participants']


def test_research_assistant_documentation_leaf_infopages_render(fake_interface, monkeypatch, capsys):
    captured = {}

    def capture(self, menu_options, submenu=True, recommended_actions=None, **kw):
        captured['menu_options'] = menu_options
        return True

    monkeypatch.setattr(_research_assistant_documentation, 'print_menu_options', capture)
    _research_assistant_documentation.research_assistant_documentation(fake_interface)
    top_level = captured['menu_options']

    top_level['terminals']['menu_caller'](fake_interface)
    assert "four terminal prompts" in capsys.readouterr().out

    top_level['task management']['menu_caller'](fake_interface)
    assert "task management system" in capsys.readouterr().out


def test_research_assistant_documentation_navigation_advanced_missing_self_param(fake_interface, monkeypatch):
    """BUG (documented, not fixed): navigation_advanced() is defined with no
    parameters (help/_research_assistant_documentation.py, ~line 26), unlike
    every other menu_caller in this file, which all take `self`. The real
    dispatch path (utils/_menu_navigation.py goto_menu() -> menu_caller(self))
    always calls it with one positional arg, so selecting "navigation
    advanced" from the RA help menu raises TypeError instead of showing its
    content; goto_menu's own try/except silently swallows it into a generic
    "An error occurred while navigating to the menu" message, so the content
    is simply unreachable from the running interface. This test pins the
    underlying TypeError so a future fix is visible.
    """
    captured = {}

    def capture(self, menu_options, submenu=True, recommended_actions=None, **kw):
        captured['menu_options'] = menu_options
        return True

    monkeypatch.setattr(_research_assistant_documentation, 'print_menu_options', capture)
    _research_assistant_documentation.research_assistant_documentation(fake_interface)
    menu_caller = captured['menu_options']['navigation advanced']['menu_caller']

    with pytest.raises(TypeError):
        menu_caller(fake_interface)
