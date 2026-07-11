"""Tests for _menu_helper.py: module globals, setter functions, and
uiconfig.txt param load/save.

All the file I/O here resolves paths via ui_state.repo_root (see
user_interface_menus/_ui_state.py) -- every test points that at a
fabricated fake repo layout under tmp_path rather than touching the real
repo's config/logs directories.
"""
import os
import time
from collections import deque

import pytest

import user_interface_menus._menu_helper as menu_helper


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """Fabricates a fake repo checkout: <root>/config, <root>/logs/
    interface_logs -- matching the paths _menu_helper.py resolves via
    ui_state.repo_root.
    """
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "logs" / "interface_logs").mkdir(parents=True)
    monkeypatch.setattr(menu_helper.ui_state, 'repo_root', tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _no_real_terminal(monkeypatch):
    """load_params' clear() touches a real terminal (os.system('clear'))
    that would spam output under plain pytest; get_cursor_position is
    neutralized defensively for any other call path that might reach it.
    Neutralize them; behavior of the terminal-facing code itself is covered
    by test_display.py.
    """
    import user_interface_menus.utils._display as _display

    # get_cursor_position is defined in _display.py; other code looks it up
    # in that module's own globals, not menu_helper's star-imported name --
    # patch the defining module.
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
# url_segment
#
# Regression tests for a real bug found by an external adversarial review:
# self.api()'s endpoint strings are plain f-strings with no encoding at
# all. A '#' in a free-text value starts a URL fragment -- confirmed live
# that `requests` silently truncates everything from the '#' onward before
# the request is even sent (data corruption, not a visible error). A '/'
# in a value splits it into an extra, unintended path segment -- confirmed
# that Flask's default route converters don't span multiple segments, so
# this fails the route match instead.

def test_url_segment_encodes_hash():
    assert menu_helper.url_segment('AB#CD') == 'AB%23CD'


def test_url_segment_encodes_slash():
    assert menu_helper.url_segment('AB/CD') == 'AB%2FCD'


def test_url_segment_leaves_colon_unencoded():
    """Task times are 'HH:MM:SS' -- a literal ':' in a single path segment
    isn't a route-splitting or truncation risk for Flask's default
    converter or `requests`, so it stays readable rather than becoming
    '00%3A00%3A00'."""
    assert menu_helper.url_segment('09:00:00') == '09:00:00'


def test_url_segment_leaves_plain_alphanumeric_unchanged():
    assert menu_helper.url_segment('000000000') == '000000000'
    assert menu_helper.url_segment('CHECK_SYSTEM') == 'CHECK_SYSTEM'


def test_url_segment_coerces_non_string_input():
    assert menu_helper.url_segment(15) == '15'


def test_url_segment_closes_the_actual_truncation_and_splitting_bugs():
    """End-to-end proof (not just a unit test of the function in
    isolation): builds the exact same kind of endpoint string a menu
    call site does, both unencoded (demonstrating the original bugs) and
    url_segment()-encoded (demonstrating the fix), and inspects what
    `requests` actually puts on the wire.
    """
    import requests

    unencoded = requests.Request(
        'PUT', f"http://localhost:5000/participants/update_participant/1/initials/AB#CD"
    ).prepare()
    assert unencoded.path_url == '/participants/update_participant/1/initials/AB'  # truncated -- the bug

    encoded = requests.Request(
        'PUT',
        f"http://localhost:5000/participants/update_participant/"
        f"{menu_helper.url_segment('1')}/{menu_helper.url_segment('initials')}/{menu_helper.url_segment('AB#CD')}",
    ).prepare()
    assert encoded.path_url == '/participants/update_participant/1/initials/AB%23CD'  # preserved -- the fix


# ------------------------------------------------------------
# add_recent_command


def test_add_recent_command_appends():
    menu_helper.add_recent_command("foo")
    assert menu_helper.ui_state.recent_commands == ["foo"]


def test_add_recent_command_dedups():
    menu_helper.add_recent_command("foo")
    menu_helper.add_recent_command("foo")
    assert menu_helper.ui_state.recent_commands == ["foo"]


def test_add_recent_command_excludes_recent_and_command():
    menu_helper.add_recent_command("recent")
    menu_helper.add_recent_command("command")
    assert menu_helper.ui_state.recent_commands == []


def test_add_recent_command_caps_at_ten_fifo():
    for i in range(11):
        menu_helper.add_recent_command(f"cmd{i}")
    assert len(menu_helper.ui_state.recent_commands) == 10
    # cmd0 was the first in, should have been popped
    assert "cmd0" not in menu_helper.ui_state.recent_commands
    assert "cmd10" in menu_helper.ui_state.recent_commands


# ------------------------------------------------------------
# local menu options


def test_set_and_get_local_menu_options():
    options = {"a": {"description": "A", "menu_caller": lambda self: None}}
    menu_helper.set_local_menu_options("mymenu", options)
    assert menu_helper.ui_state.current_menu == "mymenu"
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
    assert menu_helper.ui_state.window_width == 100
    assert (fake_repo / "config" / "uiconfig.txt").exists()


def test_set_window_width_invalid_leaves_unchanged(fake_repo, capsys):
    original = menu_helper.ui_state.window_width
    menu_helper.set_window_width(-5)
    assert menu_helper.ui_state.window_width == original
    assert "Error" in capsys.readouterr().out


def test_set_window_height_valid(fake_repo):
    menu_helper.set_window_height(30)
    assert menu_helper.ui_state.window_height == 30


def test_set_window_height_invalid_leaves_unchanged(fake_repo):
    original = menu_helper.ui_state.window_height
    menu_helper.set_window_height(0)
    assert menu_helper.ui_state.window_height == original


def test_toggle_right_align(fake_repo):
    original = menu_helper.ui_state.right_align
    menu_helper.toggle_right_align()
    assert menu_helper.ui_state.right_align is (not original)
    menu_helper.toggle_right_align()
    assert menu_helper.ui_state.right_align is original


def test_set_show_readme(fake_repo):
    menu_helper.set_show_readme(False)
    assert menu_helper.ui_state.show_readme is False


def test_toggle_color_output(fake_repo):
    original = menu_helper.ui_state.color_on
    menu_helper.toggle_color_output(FakeApp())
    assert menu_helper.ui_state.color_on is (not original)


def test_set_related_options_threshold(fake_repo):
    menu_helper.set_related_options_threshold(0.5)
    assert menu_helper.ui_state.related_options_threshold == 0.5


def test_set_best_options_threshold(fake_repo):
    menu_helper.set_best_options_threshold(0.9)
    assert menu_helper.ui_state.best_options_threshold == 0.9


def test_set_assistant_type_speed_valid(fake_repo, capsys):
    menu_helper.set_assistant_type_speed(0.03)
    assert menu_helper.ui_state.assistant_type_speed == 0.03


def test_set_assistant_type_speed_invalid_leaves_unchanged(fake_repo):
    original = menu_helper.ui_state.assistant_type_speed
    menu_helper.set_assistant_type_speed(-1)
    assert menu_helper.ui_state.assistant_type_speed == original


def test_set_menu_delay_valid(fake_repo):
    menu_helper.set_menu_delay(1.5)
    assert menu_helper.ui_state.menu_delay == 1.5


def test_set_menu_delay_rejects_negative(fake_repo):
    original = menu_helper.ui_state.menu_delay
    menu_helper.set_menu_delay(-1)
    assert menu_helper.ui_state.menu_delay == original


def test_set_timeout_valid(fake_repo):
    menu_helper.set_timeout(20)
    assert menu_helper.ui_state.timeout == 20


def test_set_timeout_rejects_non_positive(fake_repo):
    original = menu_helper.ui_state.timeout
    menu_helper.set_timeout(0)
    assert menu_helper.ui_state.timeout == original


# ------------------------------------------------------------
# save_params / load_params round trip


def test_save_params_writes_expected_format(fake_repo):
    menu_helper.ui_state.window_width = 120
    menu_helper.ui_state.window_height = 40
    menu_helper.ui_state.right_align = True
    menu_helper.ui_state.related_options_threshold = 0.3
    menu_helper.ui_state.best_options_threshold = 0.7
    menu_helper.ui_state.assistant_type_speed = 0.015
    menu_helper.ui_state.show_readme = True
    menu_helper.ui_state.color_on = True
    menu_helper.ui_state.menu_delay = 0.5
    menu_helper.ui_state.timeout = 10

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
        "SHOW_README=False\n"
        "COLOR_ON=False\n"
        "MENU_DELAY=0.1\n"
        "TIMEOUT=5\n"
        "ASSISTANT_TYPE_SPEED=0.02\n"
    )
    menu_helper.load_params()
    assert menu_helper.ui_state.window_width == 90
    assert menu_helper.ui_state.window_height == 25
    assert menu_helper.ui_state.related_options_threshold == 0.4
    assert menu_helper.ui_state.best_options_threshold == 0.8
    assert menu_helper.ui_state.show_readme is False
    assert menu_helper.ui_state.color_on is False
    assert menu_helper.ui_state.menu_delay == 0.1
    assert menu_helper.ui_state.timeout == 5
    assert menu_helper.ui_state.assistant_type_speed == 0.02


def test_load_params_rejects_out_of_range_window_width(fake_repo):
    # Unlike most other fields, WINDOW_WIDTH's out-of-range branch has no
    # `else` clause -- it silently no-ops (no "INVALID" print) rather than
    # reporting the rejection, inconsistent with e.g. RELATED_OPTIONS_THRESHOLD
    # below. Documenting current behavior, not fixing the inconsistency.
    menu_helper.ui_state.window_width = 155
    (fake_repo / "config" / "uiconfig.txt").write_text("WINDOW_WIDTH=300\n")
    menu_helper.load_params()
    assert menu_helper.ui_state.window_width == 155


def test_load_params_rejects_out_of_range_threshold(fake_repo):
    menu_helper.ui_state.related_options_threshold = 0.3
    (fake_repo / "config" / "uiconfig.txt").write_text(
        "RELATED_OPTIONS_THRESHOLD=1.5\n"
    )
    menu_helper.load_params()
    assert menu_helper.ui_state.related_options_threshold == 0.3


def test_load_params_rejects_non_numeric_value(fake_repo, capsys):
    menu_helper.ui_state.timeout = 10
    (fake_repo / "config" / "uiconfig.txt").write_text("TIMEOUT=notanumber\n")
    menu_helper.load_params()
    assert menu_helper.ui_state.timeout == 10
    assert "INVALID" in capsys.readouterr().out


def test_load_params_right_align_sets_directly_from_file(fake_repo):
    """Regression test for a fixed bug: RIGHT_ALIGN used to only ever be
    toggled (never set) when the file said "False", implicitly assuming the
    in-memory value was currently True -- a file value of "True" was a
    silent no-op regardless of current state. Now set directly from the
    file value in both directions, like every other field.
    """
    menu_helper.ui_state.right_align = True
    (fake_repo / "config" / "uiconfig.txt").write_text("RIGHT_ALIGN=False\n")
    menu_helper.load_params()
    assert menu_helper.ui_state.right_align is False

    menu_helper.ui_state.right_align = False
    (fake_repo / "config" / "uiconfig.txt").write_text("RIGHT_ALIGN=True\n")
    menu_helper.load_params()
    assert menu_helper.ui_state.right_align is True


# ------------------------------------------------------------
# interface log


def test_write_and_read_interface_log(fake_repo):
    menu_helper.write_to_interface_log("hello")
    menu_helper.write_to_interface_log("world")
    content = menu_helper.read_from_interface_log()
    assert content == "hello\nworld\n"


def test_write_to_interface_log_creates_missing_directory(tmp_path, monkeypatch):
    """Regression test for a fixed bug: write_to_interface_log() opened
    "../logs/interface_logs/test_interface_log.txt" directly with no
    os.makedirs() first, unlike the analogous server-side logging functions
    in run_prism.py -- on a fresh checkout (logs/interface_logs/ is
    git-ignored and doesn't exist until something creates it), this raised
    FileNotFoundError, caught by the broad except and printed as "Error:
    Could not write to log file: ..." instead of writing the entry.
    """
    (tmp_path / "logs").mkdir(parents=True)  # logs/ exists, interface_logs/ deliberately does not
    monkeypatch.setattr(menu_helper.ui_state, 'repo_root', tmp_path)

    menu_helper.write_to_interface_log("hello")

    assert (tmp_path / "logs" / "interface_logs" / "test_interface_log.txt").exists()
    content = menu_helper.read_from_interface_log()
    assert content == "hello\n"


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
    assert menu_helper.ui_state.menu_options == sentinel


# ------------------------------------------------------------
# read_me / README -- relocated here (2026-07-10) from the now-removed
# help/_help_menu.py: prism_interface.py imports README directly to show it
# on startup when SHOW_README is True, so this content isn't part of the
# help-menu navigation tree that was removed.


def test_read_me_prints_lines(fake_interface, capsys):
    menu_helper.read_me(fake_interface)
    out = capsys.readouterr().out
    assert "command" in out


def test_read_me_skipped_when_commands_queue_active(fake_interface, capsys):
    fake_interface.commands_queue.append('pending')
    menu_helper.read_me(fake_interface)
    assert capsys.readouterr().out == ""
