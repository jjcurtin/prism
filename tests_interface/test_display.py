"""Tests for _display.py, the Linux interface's text/ANSI display layer.

Most of this module is pure-ish print/formatting logic that runs fine under
plain pytest. A few functions talk to a *real* terminal (get_cursor_position
does an ANSI query-response round trip over stdin/stdout; several others
build on it via clear_column). Those are covered by monkeypatching the
terminal-facing primitives (kbhit/getwch/raw_mode from _keyboard, or
get_cursor_position/move_cursor directly) rather than driving a real PTY --
see the module docstring notes inline below for why.

Module globals consumed by _display.py (WINDOW_WIDTH, COLOR_ON, RIGHT_ALIGN,
RECENT_COMMANDS, ASSISTANT_TYPE_SPEED) live in user_interface_menus._menu_helper
and are re-imported fresh (`from ... import X`) inside each function body, so
mutating the module's attributes directly (not the `from` import) takes
effect immediately -- no reload needed.
"""
import builtins
import contextlib
import re
import types

import pytest

import user_interface_menus._menu_helper as menu_helper
import user_interface_menus.utils._display as display
import user_interface_menus.utils._menu_navigation as menu_navigation

ANSI_ESCAPE_RE = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')


def strip_ansi(text):
    return ANSI_ESCAPE_RE.sub('', text)


@pytest.fixture(autouse=True)
def default_menu_globals(monkeypatch):
    """Sane, explicit defaults for the _menu_helper globals _display.py
    reads. Using monkeypatch (not direct attribute assignment) means every
    test gets these reset automatically, even ones that mutate them
    mid-test or that fail partway through."""
    monkeypatch.setattr(menu_helper, 'WINDOW_WIDTH', 80)
    monkeypatch.setattr(menu_helper, 'COLOR_ON', True)
    monkeypatch.setattr(menu_helper, 'RIGHT_ALIGN', False)
    monkeypatch.setattr(menu_helper, 'RECENT_COMMANDS', [])
    monkeypatch.setattr(menu_helper, 'ASSISTANT_TYPE_SPEED', 0.001)
    yield


@pytest.fixture
def fake_self():
    return types.SimpleNamespace(debug=False)


@contextlib.contextmanager
def _noop_raw_mode():
    yield


# ------------------------------------------------------------
# color helpers
# ------------------------------------------------------------

@pytest.mark.parametrize("fn,color_on_code,color_off_code", [
    (display.green, "\033[32m", "\033[1m"),
    (display.red, "\033[31m", "\033[1m"),
    (display.yellow, "\033[33m", "\033[4m"),
    (display.cyan, "\033[36m", ""),
    (display.white, "\033[37m", ""),
])
def test_color_helpers_color_on(fn, color_on_code, color_off_code):
    menu_helper.COLOR_ON = True
    result = fn("hi")
    assert result.startswith(color_on_code)
    assert result.endswith("\033[0m" if color_on_code != color_off_code else "")
    assert "hi" in result


@pytest.mark.parametrize("fn,color_on_code,color_off_code", [
    (display.green, "\033[32m", "\033[1m"),
    (display.red, "\033[31m", "\033[1m"),
    (display.yellow, "\033[33m", "\033[4m"),
    (display.cyan, "\033[36m", ""),
    (display.white, "\033[37m", ""),
])
def test_color_helpers_color_off(fn, color_on_code, color_off_code):
    menu_helper.COLOR_ON = False
    result = fn("hi")
    assert color_on_code not in result
    assert "hi" in result
    if color_off_code:
        assert result.startswith(color_off_code)


def test_color_helpers_default_message_is_none():
    menu_helper.COLOR_ON = True
    assert display.green() == "\033[32mNone\033[0m"


# ------------------------------------------------------------
# align()
# ------------------------------------------------------------

def test_align_left_pads_to_width(fake_self):
    menu_helper.WINDOW_WIDTH = 20
    menu_helper.RIGHT_ALIGN = False
    out = display.align(fake_self, "hello", 0, 1)
    assert out == "hello" + " " * 15
    assert len(out) == 20


def test_align_right_pads_to_width(fake_self):
    menu_helper.WINDOW_WIDTH = 20
    menu_helper.RIGHT_ALIGN = True
    out = display.align(fake_self, "hello", 0, 1)
    assert out == " " * 15 + "hello"
    assert len(out) == 20


def test_align_border_left_and_right(fake_self):
    menu_helper.WINDOW_WIDTH = 20
    menu_helper.RIGHT_ALIGN = False
    out = display.align(fake_self, "hi", 0, 1, border_left=True, border_right=True)
    assert out.startswith("| ")
    assert out.endswith(" |")
    assert len(out) == 20


def test_align_truncates_when_text_exceeds_width(fake_self):
    menu_helper.WINDOW_WIDTH = 10
    menu_helper.RIGHT_ALIGN = False
    out = display.align(fake_self, "hello world this is long", 0, 1)
    assert out == "hello worl"
    assert len(out) == 10


def test_align_locked_overrides_right_align(fake_self):
    menu_helper.WINDOW_WIDTH = 20
    # RIGHT_ALIGN is True globally, but locked + explicit align_right=False
    # should force left alignment regardless.
    menu_helper.RIGHT_ALIGN = True
    out = display.align(fake_self, "hello", 0, 1, locked=True, align_right=False)
    assert out == "hello" + " " * 15


def test_align_locked_right(fake_self):
    menu_helper.WINDOW_WIDTH = 20
    menu_helper.RIGHT_ALIGN = False
    out = display.align(fake_self, "hello", 0, 1, locked=True, align_right=True)
    assert out == " " * 15 + "hello"


def test_align_handles_ansi_escaped_text_via_formatless(fake_self):
    menu_helper.WINDOW_WIDTH = 20
    menu_helper.RIGHT_ALIGN = False
    colored = display.green("hi")
    formatless = strip_ansi(colored)
    out = display.align(fake_self, colored, 0, 1, formatless=formatless)
    # visible (formatless) length should be padded out to window_width;
    # the raw string is longer because of the embedded escape codes.
    assert strip_ansi(out).rstrip() == "hi"
    assert len(strip_ansi(out)) == 20
    assert "\033[32m" in out


def test_align_middle_screen_adjustment_two_columns(fake_self):
    # WINDOW_WIDTH=21 is not evenly divisible by 2 columns; the leftover
    # width (1) should be folded into column 0's format width.
    menu_helper.WINDOW_WIDTH = 21
    menu_helper.RIGHT_ALIGN = False
    out0 = display.align(fake_self, "a", 0, 2, window_width=10)
    out1 = display.align(fake_self, "b", 1, 2, window_width=10)
    assert len(out0) == 11
    assert len(out1) == 10


def test_align_debug_true_prints_without_raising(capsys):
    debug_self = types.SimpleNamespace(debug=True)
    menu_helper.WINDOW_WIDTH = 20
    menu_helper.RIGHT_ALIGN = False
    display.align(debug_self, "hello", 0, 1)
    captured = capsys.readouterr()
    assert "size of window" in captured.out


# ------------------------------------------------------------
# display_in_columns()
# ------------------------------------------------------------

def test_display_in_columns_prints_joined_row_and_returns_positions(monkeypatch, fake_self, capsys):
    menu_helper.WINDOW_WIDTH = 20
    menu_helper.RIGHT_ALIGN = False
    monkeypatch.setattr(display, 'get_cursor_position', lambda: (0, 5))

    items = [{'text': 'a'}, {'text': 'b'}]
    positions, column_width = display.display_in_columns(fake_self, items)

    captured = capsys.readouterr()
    assert captured.out.strip('\n') == "a" + " " * 9 + "b" + " " * 9
    assert positions == [(0, 5), (10, 5)]
    assert column_width == 10


def test_display_in_columns_none_items_returns_error_string(fake_self):
    assert display.display_in_columns(fake_self, None) == "Error: No items to display."


def test_display_in_columns_handles_internal_exception_via_error(monkeypatch, fake_self):
    # Force an exception inside assemble_content (missing 'text' key) and
    # confirm display_in_columns funnels it through error() rather than
    # raising, returning the documented ([], 0) fallback.
    calls = []
    monkeypatch.setattr(display, 'error', lambda message="", self=None: calls.append(message))
    result = display.display_in_columns(fake_self, [{'not_text': 'a'}])
    assert result == ([], 0)
    assert calls and "Error displaying items in columns" in calls[0]


# ------------------------------------------------------------
# error() / success() / exit_menu() / exit_interface()
# ------------------------------------------------------------

def test_error_writes_log_clears_queue_and_exits(monkeypatch):
    calls = []
    monkeypatch.setattr(menu_navigation, 'clear_commands_queue', lambda self: calls.append(('cleared', self)))
    monkeypatch.setattr(menu_helper, 'write_to_interface_log', lambda msg: calls.append(('log', msg)))
    monkeypatch.setattr(display, 'exit_menu', lambda: calls.append(('exit_menu',)))

    fake = types.SimpleNamespace(commands_queue=[])
    display.error("boom", fake)

    assert ('log', 'Error: boom') in calls
    assert ('cleared', fake) in calls
    assert ('exit_menu',) in calls


def test_error_with_no_self_skips_clear_commands_queue(monkeypatch):
    calls = []
    monkeypatch.setattr(menu_navigation, 'clear_commands_queue', lambda self: calls.append('cleared'))
    monkeypatch.setattr(menu_helper, 'write_to_interface_log', lambda msg: None)
    monkeypatch.setattr(display, 'exit_menu', lambda: calls.append('exit_menu'))

    display.error("boom", None)

    assert 'cleared' not in calls
    assert 'exit_menu' in calls


def test_error_log_write_failure_is_caught(monkeypatch, capsys):
    def raise_io(msg):
        raise IOError("disk full")
    monkeypatch.setattr(menu_helper, 'write_to_interface_log', raise_io)
    monkeypatch.setattr(menu_navigation, 'clear_commands_queue', lambda self: None)
    monkeypatch.setattr(display, 'exit_menu', lambda: None)

    display.error("boom", None)
    captured = capsys.readouterr()
    assert "Could not write to log file" in captured.out


def test_success_skips_exit_menu_when_commands_queue_truthy(monkeypatch):
    calls = []
    monkeypatch.setattr(menu_helper, 'write_to_interface_log', lambda msg: None)
    monkeypatch.setattr(display, 'exit_menu', lambda: calls.append('exit_menu'))

    fake = types.SimpleNamespace(commands_queue=['pending'])
    display.success("yay", fake)
    assert calls == []


def test_success_calls_exit_menu_when_commands_queue_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(menu_helper, 'write_to_interface_log', lambda msg: None)
    monkeypatch.setattr(display, 'exit_menu', lambda: calls.append('exit_menu'))

    fake = types.SimpleNamespace(commands_queue=[])
    display.success("yay", fake)
    assert calls == ['exit_menu']


def test_success_calls_exit_menu_when_self_none(monkeypatch):
    calls = []
    monkeypatch.setattr(menu_helper, 'write_to_interface_log', lambda msg: None)
    monkeypatch.setattr(display, 'exit_menu', lambda: calls.append('exit_menu'))

    display.success("yay", None)
    assert calls == ['exit_menu']


def test_success_log_write_failure_routes_through_error(monkeypatch):
    def raise_io(msg):
        raise IOError("disk full")
    monkeypatch.setattr(menu_helper, 'write_to_interface_log', raise_io)
    calls = []
    monkeypatch.setattr(display, 'error', lambda message="", self=None: calls.append(message))

    display.success("yay", None)
    assert calls and "Could not write to log file" in calls[0]


def test_exit_menu_calls_input(monkeypatch):
    calls = []
    monkeypatch.setattr(builtins, 'input', lambda prompt="": calls.append(prompt) or "")
    display.exit_menu()
    assert len(calls) == 1
    assert "ENTER to Continue" in calls[0]


def test_exit_interface_calls_exit_with_zero(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(builtins, 'exit', lambda code=0: calls.append(code))
    display.exit_interface(None)
    assert calls == [0]
    assert "Exiting PRISM Interface" in capsys.readouterr().out


# ------------------------------------------------------------
# print_menu_header / print_dashes / print_guide_lines / print_equals
# ------------------------------------------------------------

def test_print_equals_uses_window_width(capsys):
    menu_helper.WINDOW_WIDTH = 15
    display.print_equals()
    assert capsys.readouterr().out == "=" * 15 + "\n"


def test_print_dashes_no_delay(capsys):
    menu_helper.WINDOW_WIDTH = 15
    display.print_dashes()
    assert capsys.readouterr().out == "-" * 15 + "\n"


def test_print_menu_header(monkeypatch, capsys):
    menu_helper.WINDOW_WIDTH = 20
    monkeypatch.setattr(display, 'clear', lambda: None)
    display.print_menu_header("Title")
    out = capsys.readouterr().out
    assert "Title" in out
    assert out.count("=" * 20) == 2
    assert "-" * 20 in out


def test_print_guide_lines_dashes(capsys):
    menu_helper.WINDOW_WIDTH = 20
    menu_helper.COLOR_ON = False
    display.print_guide_lines(2, "dashes", 2)
    out = capsys.readouterr().out
    assert out.strip('\n') == "|--------||--------|"


def test_print_guide_lines_dots(capsys):
    menu_helper.WINDOW_WIDTH = 20
    menu_helper.COLOR_ON = False
    display.print_guide_lines(2, "dots", 2)
    out = capsys.readouterr().out
    assert out.strip('\n') == "|        ||        |"


def test_print_guide_lines_color_on_embeds_ansi(capsys):
    menu_helper.WINDOW_WIDTH = 20
    menu_helper.COLOR_ON = True
    display.print_guide_lines(2, "dashes", 2)
    out = capsys.readouterr().out
    assert "\033[1;3" in out


def test_print_guide_lines_exceeding_max_divisions_calls_error(monkeypatch):
    calls = []
    monkeypatch.setattr(display, 'error', lambda message="", self=None: calls.append(message))
    display.print_guide_lines(4, "dashes", 2)
    assert calls and "Maximum divisions is 3" in calls[0]


# ------------------------------------------------------------
# ANSI helper functions
# ------------------------------------------------------------

def test_ansi_save_cursor(capsys):
    display.ansi_save_cursor()
    assert capsys.readouterr().out == "\033[s"


def test_ansi_restore_cursor(capsys):
    display.ansi_restore_cursor()
    assert capsys.readouterr().out == "\033[u"


def test_ansi_clear_line(capsys):
    display.ansi_clear_line()
    assert capsys.readouterr().out == "\033[2K"


def test_ansi_clear_screen(capsys):
    display.ansi_clear_screen()
    assert capsys.readouterr().out == "\033[2J"


def test_ansi_write_char(capsys):
    display.ansi_write_char("x")
    assert capsys.readouterr().out == "x"


def test_ansi_hide_cursor(capsys):
    display.ansi_hide_cursor()
    assert capsys.readouterr().out == "\033[?25l"


def test_ansi_show_cursor(capsys):
    display.ansi_show_cursor()
    assert capsys.readouterr().out == "\033[?25h"


def test_ansi_write_str(capsys):
    display.ansi_write_str("hello world")
    assert capsys.readouterr().out == "hello world"


# ------------------------------------------------------------
# move_cursor()
# ------------------------------------------------------------

def test_move_cursor_writes_position_code(capsys, fake_self):
    display.move_cursor(fake_self, 4, 9)
    assert capsys.readouterr().out == "\033[10;5H"


def test_move_cursor_except_branch_with_debug_attr_present(monkeypatch, capsys):
    # Force just the ANSI positioning write to fail so the except branch
    # runs, while leaving the except block's own print() functional --
    # self.debug exists here, so this is the safe case. (See report: a
    # self WITHOUT .debug would raise AttributeError from inside this
    # except block itself -- a latent fragility, not exercised here since
    # it's out of scope to "fix".)
    debug_self = types.SimpleNamespace(debug=True)

    import sys as _sys
    real_write = _sys.stdout.write

    def flaky_write(s, *_a, **_k):
        if s.startswith("\033["):
            raise OSError("broken pipe")
        return real_write(s, *_a, **_k)

    monkeypatch.setattr(_sys.stdout, 'write', flaky_write)
    # should not raise
    display.move_cursor(debug_self, 1, 1)
    assert "error moving: 1, 1" in capsys.readouterr().out


# ------------------------------------------------------------
# save_cursor_pos / restore_cursor_pos / clear_column
# ------------------------------------------------------------

def test_save_cursor_pos_initializes_list(fake_self):
    display.save_cursor_pos(fake_self, 1, 2)
    assert fake_self.saved_positions == [(1, 2)]
    display.save_cursor_pos(fake_self, 3, 4)
    assert fake_self.saved_positions == [(1, 2), (3, 4)]


def test_restore_cursor_pos_noop_when_no_saved_positions(fake_self):
    # no .saved_positions attribute at all yet
    display.restore_cursor_pos(fake_self)
    assert not hasattr(fake_self, 'saved_positions')


def test_restore_cursor_pos_noop_when_empty_list(fake_self):
    fake_self.saved_positions = []
    display.restore_cursor_pos(fake_self)  # should not raise / index error


def test_restore_cursor_pos_moves_to_indexed_position(monkeypatch, fake_self):
    calls = []
    monkeypatch.setattr(display, 'move_cursor', lambda self, x, y: calls.append((x, y)))
    fake_self.saved_positions = [(1, 2), (3, 4)]
    display.restore_cursor_pos(fake_self, 0)
    assert calls == [(1, 2)]


def test_clear_column_bookkeeping(monkeypatch, fake_self):
    monkeypatch.setattr(display, 'get_cursor_position', lambda: (5, 6))
    move_calls = []
    monkeypatch.setattr(display, 'move_cursor', lambda self, x, y: move_calls.append((x, y)))

    display.clear_column(fake_self, 0, 0, 3, 2)

    # saves current position, blanks each row, then restores to it
    assert fake_self.saved_positions == [(5, 6)]
    assert move_calls == [(0, 0), (0, 1), (5, 6)]


def test_clear_column_skips_save_when_cursor_position_unknown(monkeypatch, fake_self):
    monkeypatch.setattr(display, 'get_cursor_position', lambda: (None, None))
    move_calls = []
    monkeypatch.setattr(display, 'move_cursor', lambda self, x, y: move_calls.append((x, y)))

    display.clear_column(fake_self, 0, 0, 2, 1)

    assert not hasattr(fake_self, 'saved_positions')
    assert move_calls == [(0, 0)]  # restore_cursor_pos is a no-op (empty list)


# ------------------------------------------------------------
# toggle_debug_mode() / clear()
# ------------------------------------------------------------

def test_toggle_debug_mode(fake_self):
    assert fake_self.debug is False
    display.toggle_debug_mode(fake_self)
    assert fake_self.debug is True
    display.toggle_debug_mode(fake_self)
    assert fake_self.debug is False


def test_clear_calls_os_system_with_platform_dependent_command(monkeypatch):
    import os as _os
    calls = []
    monkeypatch.setattr(_os, 'system', lambda cmd: calls.append(cmd))
    display.clear()
    expected = 'cls' if _os.name == 'nt' else 'clear'
    assert calls == [expected]


# ------------------------------------------------------------
# get_cursor_position() -- parsing logic only, terminal I/O mocked out
# ------------------------------------------------------------

def _feed(monkeypatch, chars):
    """Feed a canned byte sequence into get_cursor_position()'s read loop,
    one character per kbhit()/getwch() poll, and no-op raw_mode() (which
    otherwise calls real termios and fails outside a tty)."""
    remaining = list(chars)
    monkeypatch.setattr(display, 'raw_mode', _noop_raw_mode)
    monkeypatch.setattr(display, 'kbhit', lambda: len(remaining) > 0)
    monkeypatch.setattr(display, 'getwch', lambda: remaining.pop(0))


def test_get_cursor_position_parses_well_formed_response(monkeypatch, capsys):
    _feed(monkeypatch, "\x1b[24;80R")
    x, y = display.get_cursor_position()
    assert (x, y) == (79, 23)  # 0-indexed


def test_get_cursor_position_malformed_response_returns_none_none(monkeypatch):
    _feed(monkeypatch, "R")
    x, y = display.get_cursor_position()
    assert (x, y) is (None, None) or (x, y) == (None, None)


# ------------------------------------------------------------
# syntax_highlight() / syntax_highlight_string()
# ------------------------------------------------------------

def test_syntax_highlight_color_on_writes_composed_line(monkeypatch, fake_self, capsys):
    monkeypatch.setattr(display, 'get_cursor_position', lambda: (0, 5))
    move_calls = []
    monkeypatch.setattr(display, 'move_cursor', lambda self, x, y: move_calls.append((x, y)))
    menu_helper.COLOR_ON = True

    display.syntax_highlight(fake_self, prompt="p> ", items=[(display.green, "hi")])

    out = capsys.readouterr().out
    assert "p> " in out
    assert "hi" in out
    assert move_calls == [(0, 4)]


def test_syntax_highlight_color_off_is_noop(monkeypatch, fake_self, capsys):
    monkeypatch.setattr(display, 'get_cursor_position', lambda: (0, 5))
    monkeypatch.setattr(display, 'move_cursor', lambda self, x, y: (_ for _ in ()).throw(AssertionError("should not be called")))
    menu_helper.COLOR_ON = False

    result = display.syntax_highlight(fake_self, prompt="p> ", items=[(display.green, "hi")])

    assert result is None
    assert capsys.readouterr().out == ""


def test_syntax_highlight_string_not_in_place(monkeypatch, fake_self, capsys):
    monkeypatch.setattr(display, 'get_cursor_position', lambda: (0, 5))
    move_calls = []
    monkeypatch.setattr(display, 'move_cursor', lambda self, x, y: move_calls.append((x, y)))
    menu_helper.COLOR_ON = True

    display.syntax_highlight_string(fake_self, input_string="/foo", prompt="p> ", items=[(display.green, "/foo")], in_place=False)

    out = capsys.readouterr().out
    assert "p> " in out
    assert move_calls == [(0, 4)]


def test_syntax_highlight_string_in_place(monkeypatch, fake_self, capsys):
    monkeypatch.setattr(display, 'get_cursor_position', lambda: (0, 5))
    move_calls = []
    monkeypatch.setattr(display, 'move_cursor', lambda self, x, y: move_calls.append((x, y)) or None)
    clear_calls = []
    monkeypatch.setattr(display, 'ansi_clear_line', lambda: clear_calls.append(True))
    menu_helper.COLOR_ON = True

    display.syntax_highlight_string(fake_self, input_string="/foo", prompt="p> ", items=[(display.green, "/foo")], in_place=True)

    assert clear_calls == [True]
    assert move_calls == [(0, 5)]  # move_cursor returns falsy -> while loop runs once


def test_syntax_highlight_string_color_off_is_noop(fake_self, capsys):
    menu_helper.COLOR_ON = False
    result = display.syntax_highlight_string(fake_self, input_string="/foo", prompt="p> ", items=[(display.green, "/foo")])
    assert result is None
    assert capsys.readouterr().out == ""


def test_syntax_highlight_string_none_items_is_noop(fake_self, capsys):
    menu_helper.COLOR_ON = True
    result = display.syntax_highlight_string(fake_self, input_string="/foo", prompt="p> ", items=None)
    assert result is None
    assert capsys.readouterr().out == ""


# ------------------------------------------------------------
# assistant_header_write smoke tests -- typewriter effect with real
# time.sleep() calls normally; these monkeypatch time.sleep to a no-op and
# kbhit to never-interrupt, and confirm the function runs to completion
# without raising. clear_column (called internally) needs
# get_cursor_position mocked too, or its inner ANSI-query wait loop spins
# forever once kbhit() is pinned to a constant.
# ------------------------------------------------------------

@pytest.fixture
def patched_terminal(monkeypatch):
    """Common terminal-facing patches for the typewriter-effect smoke
    tests: no-op raw_mode (avoids real termios calls outside a tty),
    no-op time.sleep (avoids real wall-clock cost), and a fixed cursor
    position (avoids clear_column's internal ANSI query hanging)."""
    monkeypatch.setattr(display, 'raw_mode', _noop_raw_mode)
    monkeypatch.setattr(display.time, 'sleep', lambda s: None)
    monkeypatch.setattr(display, 'get_cursor_position', lambda: (0, 5))
    return monkeypatch


def test_assistant_header_write_smoke(patched_terminal, fake_self):
    patched_terminal.setattr(display, 'kbhit', lambda: False)
    menu_helper.WINDOW_WIDTH = 20
    menu_helper.ASSISTANT_TYPE_SPEED = 0.001
    # should run to completion without raising
    display.assistant_header_write(fake_self, ["hi there"])


def test_assistant_header_write_enter_interrupts_early(patched_terminal, fake_self, capsys):
    patched_terminal.setattr(display, 'kbhit', lambda: True)
    patched_terminal.setattr(display, 'getwch', lambda: '\r')
    menu_helper.WINDOW_WIDTH = 20

    display.assistant_header_write(fake_self, ["a much longer line of text than one char"])

    out = capsys.readouterr().out
    # only the initial clear_column blank + cursor show/restore happened;
    # none of the message body characters got written.
    assert "a much longer line" not in out
