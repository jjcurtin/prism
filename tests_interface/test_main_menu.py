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
    assert kwargs['recommended_actions'] == ['participants', 'tasks']
