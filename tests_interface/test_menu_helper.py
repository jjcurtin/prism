"""Tests for _menu_helper.py: module globals, setter functions, macro
persistence (saved_macros.txt), and uiconfig.txt param load/save.

All the file I/O here uses hardcoded *relative* paths (e.g.
"../config/saved_macros.txt", "user_interface_menus/utils/system_tests.txt")
that assume cwd is the repo's src/ directory -- so every test chdirs into a
fabricated fake repo layout under tmp_path rather than touching the real
repo's config/logs directories.
"""
import os
import time
from collections import deque

import pytest

import user_interface_menus._menu_helper as menu_helper
from user_interface_menus.utils._menu_navigation import CommandInjector


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """Fabricates a fake repo checkout: <root>/src (cwd), <root>/config,
    <root>/logs/interface_logs, <root>/src/user_interface_menus/utils --
    matching the relative-path assumptions baked into _menu_helper.py.
    """
    src_dir = tmp_path / "src"
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "logs" / "interface_logs").mkdir(parents=True)
    (src_dir / "user_interface_menus" / "utils").mkdir(parents=True)
    monkeypatch.chdir(src_dir)
    return tmp_path


@pytest.fixture(autouse=True)
def _no_real_terminal(monkeypatch):
    """Several call paths here (macro_search -> display_in_columns,
    load_params' clear()) touch a real terminal (ANSI cursor queries,
    os.system('clear')) that would hang or spam output under plain pytest.
    Neutralize them; behavior of the terminal-facing code itself is covered
    by test_display.py.
    """
    import user_interface_menus.utils._display as _display

    # get_cursor_position is defined in _display.py; display_in_columns
    # (called by macro_search) looks it up in that module's own globals,
    # not menu_helper's star-imported name -- patch the defining module.
    monkeypatch.setattr(_display, "get_cursor_position", lambda *a, **k: (0, 0))
    monkeypatch.setattr(os, "system", lambda *a, **k: 0)
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)


class FakeApp:
    """Minimal `self` for functions that call success()/error(): needs a
    truthy commands_queue so success()'s `if self is None or not
    self.commands_queue: exit_menu()` branch is skipped (exit_menu() calls
    a blocking input() -- the autouse _menu_helper_state fixture in
    conftest.py also neutralizes builtins.input, but skipping it entirely
    is cleaner where possible).
    """

    def __init__(self):
        self.commands_queue = deque(["placeholder"])
        self.debug = False


# ------------------------------------------------------------
# add_recent_command


def test_add_recent_command_appends():
    menu_helper.add_recent_command("foo")
    assert menu_helper.RECENT_COMMANDS == ["foo"]


def test_add_recent_command_dedups():
    menu_helper.add_recent_command("foo")
    menu_helper.add_recent_command("foo")
    assert menu_helper.RECENT_COMMANDS == ["foo"]


def test_add_recent_command_excludes_recent_and_command():
    menu_helper.add_recent_command("recent")
    menu_helper.add_recent_command("command")
    assert menu_helper.RECENT_COMMANDS == []


def test_add_recent_command_caps_at_ten_fifo():
    for i in range(11):
        menu_helper.add_recent_command(f"cmd{i}")
    assert len(menu_helper.RECENT_COMMANDS) == 10
    # cmd0 was the first in, should have been popped
    assert "cmd0" not in menu_helper.RECENT_COMMANDS
    assert "cmd10" in menu_helper.RECENT_COMMANDS


# ------------------------------------------------------------
# add_user_defined_global_command


def test_add_user_defined_global_command_accepts_valid_identifier():
    ok = menu_helper.add_user_defined_global_command("mymacro", "/help", "desc")
    assert ok is True
    assert "mymacro" in menu_helper._menu_options
    entry = menu_helper._menu_options["mymacro"]
    assert entry["description"] == "desc"
    assert isinstance(entry["menu_caller"], CommandInjector)


def test_add_user_defined_global_command_defaults_description_to_command_string():
    menu_helper.add_user_defined_global_command("mymacro", "/help")
    assert menu_helper._menu_options["mymacro"]["description"] == "/help"


@pytest.mark.parametrize("identifier", ["y", "n", "yes", "no", "0", "999", "a", "Z"])
def test_add_user_defined_global_command_rejects_banned_identifiers(identifier):
    ok = menu_helper.add_user_defined_global_command(identifier, "/help")
    assert ok is False
    assert menu_helper._menu_options is None or identifier not in menu_helper._menu_options


@pytest.mark.parametrize("identifier", ["a/b", "a?b", "/leading", "trailing?"])
def test_add_user_defined_global_command_rejects_banned_characters(identifier):
    ok = menu_helper.add_user_defined_global_command(identifier, "/help")
    assert ok is False


def test_add_user_defined_global_command_rejects_duplicate():
    assert menu_helper.add_user_defined_global_command("mymacro", "/help") is True
    assert menu_helper.add_user_defined_global_command("mymacro", "/other") is False
    # original entry preserved, not overwritten
    assert menu_helper._menu_options["mymacro"]["description"] == "/help"


# ------------------------------------------------------------
# local menu options


def test_set_and_get_local_menu_options():
    options = {"a": {"description": "A", "menu_caller": lambda self: None}}
    menu_helper.set_local_menu_options("mymenu", options)
    assert menu_helper.current_menu == "mymenu"
    assert menu_helper.get_local_menu_options() == options


def test_print_local_menu_options_empty(capsys):
    menu_helper.print_local_menu_options()
    out = capsys.readouterr().out
    assert "Local menu options" not in out


def test_print_local_menu_options_lists_keys(capsys):
    menu_helper.set_local_menu_options("mymenu", {"foo": {}, "bar": {}})
    menu_helper.print_local_menu_options()
    out = capsys.readouterr().out
    assert "Local menu options" in out
    assert "foo" in out
    assert "bar" in out


# ------------------------------------------------------------
# setters (each calls save_params(), which writes ../config/uiconfig.txt)


def test_set_window_width_valid(fake_repo):
    menu_helper.set_window_width(100)
    assert menu_helper.WINDOW_WIDTH == 100
    assert (fake_repo / "config" / "uiconfig.txt").exists()


def test_set_window_width_invalid_leaves_unchanged(fake_repo, capsys):
    original = menu_helper.WINDOW_WIDTH
    menu_helper.set_window_width(-5)
    assert menu_helper.WINDOW_WIDTH == original
    assert "Error" in capsys.readouterr().out


def test_set_window_height_valid(fake_repo):
    menu_helper.set_window_height(30)
    assert menu_helper.WINDOW_HEIGHT == 30


def test_set_window_height_invalid_leaves_unchanged(fake_repo):
    original = menu_helper.WINDOW_HEIGHT
    menu_helper.set_window_height(0)
    assert menu_helper.WINDOW_HEIGHT == original


def test_toggle_right_align(fake_repo):
    original = menu_helper.RIGHT_ALIGN
    menu_helper.toggle_right_align()
    assert menu_helper.RIGHT_ALIGN is (not original)
    menu_helper.toggle_right_align()
    assert menu_helper.RIGHT_ALIGN is original


def test_set_show_readme(fake_repo):
    menu_helper.set_show_readme(False)
    assert menu_helper.SHOW_README is False


def test_toggle_color_output(fake_repo):
    original = menu_helper.COLOR_ON
    menu_helper.toggle_color_output(FakeApp())
    assert menu_helper.COLOR_ON is (not original)


def test_set_related_options_threshold(fake_repo):
    menu_helper.set_related_options_threshold(0.5)
    assert menu_helper.RELATED_OPTIONS_THRESHOLD == 0.5


def test_set_best_options_threshold(fake_repo):
    menu_helper.set_best_options_threshold(0.9)
    assert menu_helper.BEST_OPTIONS_THRESHOLD == 0.9


def test_set_assistant_temperature(fake_repo):
    menu_helper.set_assistant_temperature(0.2)
    assert menu_helper.ASSISTANT_TEMPERATURE == 0.2


def test_set_assistant_tokens(fake_repo):
    menu_helper.set_assistant_tokens(1200)
    assert menu_helper.ASSISTANT_TOKENS == 1200


def test_set_assistant_type_speed_valid(fake_repo, capsys):
    menu_helper.set_assistant_type_speed(0.03)
    assert menu_helper.ASSISTANT_TYPE_SPEED == 0.03


def test_set_assistant_type_speed_invalid_leaves_unchanged(fake_repo):
    original = menu_helper.ASSISTANT_TYPE_SPEED
    menu_helper.set_assistant_type_speed(-1)
    assert menu_helper.ASSISTANT_TYPE_SPEED == original


def test_set_menu_delay_valid(fake_repo):
    menu_helper.set_menu_delay(1.5)
    assert menu_helper.MENU_DELAY == 1.5


def test_set_menu_delay_rejects_negative(fake_repo):
    original = menu_helper.MENU_DELAY
    menu_helper.set_menu_delay(-1)
    assert menu_helper.MENU_DELAY == original


def test_set_timeout_valid(fake_repo):
    menu_helper.set_timeout(20)
    assert menu_helper.TIMEOUT == 20


def test_set_timeout_rejects_non_positive(fake_repo):
    original = menu_helper.TIMEOUT
    menu_helper.set_timeout(0)
    assert menu_helper.TIMEOUT == original


# ------------------------------------------------------------
# save_params / load_params round trip


def test_save_params_writes_expected_format(fake_repo):
    menu_helper.WINDOW_WIDTH = 120
    menu_helper.WINDOW_HEIGHT = 40
    menu_helper.RIGHT_ALIGN = True
    menu_helper.RELATED_OPTIONS_THRESHOLD = 0.3
    menu_helper.BEST_OPTIONS_THRESHOLD = 0.7
    menu_helper.ASSISTANT_TEMPERATURE = 0.7
    menu_helper.ASSISTANT_TOKENS = 600
    menu_helper.ASSISTANT_TYPE_SPEED = 0.015
    menu_helper.SHOW_README = True
    menu_helper.COLOR_ON = True
    menu_helper.MENU_DELAY = 0.5
    menu_helper.TIMEOUT = 10

    menu_helper.save_params()

    content = (fake_repo / "config" / "uiconfig.txt").read_text()
    assert "WINDOW_WIDTH=120" in content
    assert "WINDOW_HEIGHT=40" in content
    assert "RIGHT_ALIGN=True" in content
    assert "TIMEOUT=10" in content


def test_load_params_applies_valid_values(fake_repo):
    (fake_repo / "config" / "uiconfig.txt").write_text(
        "WINDOW_WIDTH=90\n"
        "WINDOW_HEIGHT=25\n"
        "RELATED_OPTIONS_THRESHOLD=0.4\n"
        "BEST_OPTIONS_THRESHOLD=0.8\n"
        "ASSISTANT_TEMPERATURE=0.5\n"
        "SHOW_README=False\n"
        "COLOR_ON=False\n"
        "ASSISTANT_TOKENS=500\n"
        "MENU_DELAY=0.1\n"
        "TIMEOUT=5\n"
        "ASSISTANT_TYPE_SPEED=0.02\n"
    )
    menu_helper.load_params()
    assert menu_helper.WINDOW_WIDTH == 90
    assert menu_helper.WINDOW_HEIGHT == 25
    assert menu_helper.RELATED_OPTIONS_THRESHOLD == 0.4
    assert menu_helper.BEST_OPTIONS_THRESHOLD == 0.8
    assert menu_helper.ASSISTANT_TEMPERATURE == 0.5
    assert menu_helper.SHOW_README is False
    assert menu_helper.COLOR_ON is False
    assert menu_helper.ASSISTANT_TOKENS == 500
    assert menu_helper.MENU_DELAY == 0.1
    assert menu_helper.TIMEOUT == 5
    assert menu_helper.ASSISTANT_TYPE_SPEED == 0.02


def test_load_params_rejects_out_of_range_window_width(fake_repo):
    # Unlike most other fields, WINDOW_WIDTH's out-of-range branch has no
    # `else` clause -- it silently no-ops (no "INVALID" print) rather than
    # reporting the rejection, inconsistent with e.g. RELATED_OPTIONS_THRESHOLD
    # below. Documenting current behavior, not fixing the inconsistency.
    menu_helper.WINDOW_WIDTH = 155
    (fake_repo / "config" / "uiconfig.txt").write_text("WINDOW_WIDTH=300\n")
    menu_helper.load_params()
    assert menu_helper.WINDOW_WIDTH == 155


def test_load_params_rejects_out_of_range_threshold(fake_repo):
    menu_helper.RELATED_OPTIONS_THRESHOLD = 0.3
    (fake_repo / "config" / "uiconfig.txt").write_text(
        "RELATED_OPTIONS_THRESHOLD=1.5\n"
    )
    menu_helper.load_params()
    assert menu_helper.RELATED_OPTIONS_THRESHOLD == 0.3


def test_load_params_rejects_non_numeric_value(fake_repo, capsys):
    menu_helper.TIMEOUT = 10
    (fake_repo / "config" / "uiconfig.txt").write_text("TIMEOUT=notanumber\n")
    menu_helper.load_params()
    assert menu_helper.TIMEOUT == 10
    assert "INVALID" in capsys.readouterr().out


def test_load_params_right_align_only_toggles_on_false(fake_repo):
    """Documents existing (fragile) behavior, not fixing it: RIGHT_ALIGN is
    never set directly from the file -- load_params() only calls
    toggle_right_align() when the file says "False", implicitly assuming
    the in-memory value is currently True. If the in-memory value is
    already False, or the file says "True", nothing happens either way.
    A file value of "True" is silently a no-op regardless of current state.
    """
    menu_helper.RIGHT_ALIGN = True
    (fake_repo / "config" / "uiconfig.txt").write_text("RIGHT_ALIGN=False\n")
    menu_helper.load_params()
    assert menu_helper.RIGHT_ALIGN is False

    menu_helper.RIGHT_ALIGN = False
    (fake_repo / "config" / "uiconfig.txt").write_text("RIGHT_ALIGN=True\n")
    menu_helper.load_params()
    # BUG (pre-existing, not fixed here): file says RIGHT_ALIGN=True but
    # nothing sets it back to True from False -- stays False.
    assert menu_helper.RIGHT_ALIGN is False


# ------------------------------------------------------------
# macro persistence (saved_macros.txt)


def test_save_macro_writes_line(fake_repo):
    menu_helper.save_macro(FakeApp(), "mymacro", "/help", "My macro")
    content = (fake_repo / "config" / "saved_macros.txt").read_text()
    assert content == "mymacro|/help|My macro\n"


def test_save_macro_defaults_description_to_command_string(fake_repo):
    menu_helper.save_macro(FakeApp(), "mymacro", "/help")
    content = (fake_repo / "config" / "saved_macros.txt").read_text()
    assert content == "mymacro|/help|/help\n"


def test_load_saved_macros_populates_menu_options(fake_repo):
    (fake_repo / "config" / "saved_macros.txt").write_text(
        "mymacro|/help|My macro\nother|/settings|Other macro\n"
    )
    menu_helper.load_saved_macros(FakeApp())
    assert "mymacro" in menu_helper._menu_options
    assert "other" in menu_helper._menu_options
    assert menu_helper._menu_options["mymacro"]["description"] == "My macro"


def test_load_saved_macros_missing_file_prints_message(fake_repo, capsys):
    menu_helper.load_saved_macros(FakeApp())
    out = capsys.readouterr().out
    assert "No saved macros found" in out


def test_load_saved_macros_also_loads_system_tests_and_utils(fake_repo):
    (fake_repo / "src" / "user_interface_menus" / "utils" / "system_tests.txt").write_text(
        "systest|/check|System test macro\n"
    )
    (fake_repo / "src" / "user_interface_menus" / "utils" / "system_utils.txt").write_text(
        "sysutil|/logs|System util macro\n"
    )
    menu_helper.load_saved_macros(FakeApp())
    assert "systest" in menu_helper._menu_options
    assert "sysutil" in menu_helper._menu_options


def test_remove_macro_deletes_entry_and_rewrites_file(fake_repo):
    (fake_repo / "config" / "saved_macros.txt").write_text(
        "mymacro|/help|My macro\nother|/settings|Other macro\n"
    )
    menu_helper.load_saved_macros(FakeApp())
    assert "mymacro" in menu_helper._menu_options

    menu_helper.remove_macro(FakeApp(), "-mymacro")

    assert "mymacro" not in menu_helper._menu_options
    remaining = (fake_repo / "config" / "saved_macros.txt").read_text()
    assert "mymacro" not in remaining
    assert "other|/settings|Other macro" in remaining


def test_remove_macro_noop_when_identifier_unknown(fake_repo):
    (fake_repo / "config" / "saved_macros.txt").write_text("other|/settings|Other macro\n")
    menu_helper.load_saved_macros(FakeApp())
    menu_helper.remove_macro(FakeApp(), "-doesnotexist")
    # file untouched
    content = (fake_repo / "config" / "saved_macros.txt").read_text()
    assert content == "other|/settings|Other macro\n"


def test_macro_search_by_substring(fake_repo, capsys):
    (fake_repo / "config" / "saved_macros.txt").write_text(
        "mymacro|/help|My macro\nother|/settings|Other macro\n"
    )
    menu_helper.macro_search(FakeApp(), "?my")
    out = capsys.readouterr().out
    assert "mymacro" in out
    assert "Success" in out


def test_macro_search_all(fake_repo, capsys):
    (fake_repo / "config" / "saved_macros.txt").write_text(
        "mymacro|/help|My macro\nother|/settings|Other macro\n"
    )
    menu_helper.macro_search(FakeApp(), "?", all=True)
    out = capsys.readouterr().out
    assert "mymacro" in out
    assert "other" in out


def test_macro_search_no_matches(fake_repo, capsys):
    # query must be dissimilar enough to also clear the fuzzy-match cutoff
    # (RELATED_OPTIONS_THRESHOLD=0.3, per conftest's autouse fixture) --
    # short/partially-overlapping queries like "zzzznomatch" vs "other"
    # still register as a fuzzy match via difflib.get_close_matches.
    (fake_repo / "config" / "saved_macros.txt").write_text("other|/settings|Other macro\n")
    menu_helper.macro_search(FakeApp(), "?completelydifferentxyz123")
    out = capsys.readouterr().out
    assert "No matching macros found" in out


def test_macro_search_missing_file(fake_repo, capsys):
    menu_helper.macro_search(FakeApp(), "?anything")
    out = capsys.readouterr().out
    assert "No saved macros found" in out


# ------------------------------------------------------------
# interface log


def test_write_and_read_interface_log(fake_repo):
    menu_helper.write_to_interface_log("hello")
    menu_helper.write_to_interface_log("world")
    content = menu_helper.read_from_interface_log()
    assert content == "hello\nworld\n"


def test_read_from_interface_log_missing_file(fake_repo, capsys):
    result = menu_helper.read_from_interface_log()
    assert result == ""
    assert "not found" in capsys.readouterr().out


# ------------------------------------------------------------
# load_menus


def test_load_menus_calls_init_commands(fake_repo, monkeypatch):
    sentinel = {"help": {"description": "Help", "menu_caller": lambda self: None}}
    monkeypatch.setattr(
        "user_interface_menus.utils._commands.init_commands", lambda: sentinel
    )
    menu_helper.load_menus()
    assert menu_helper._menu_options == sentinel
