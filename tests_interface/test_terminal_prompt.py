"""Tests for print_fixed_terminal_prompt() (utils/_display.py) -- the
raw-mode interactive line editor behind the `prism> ` prompt. Needs a real
PTY (raw_mode()'s termios/cbreak mode doesn't work over a plain pipe), so
this spawns the module under pexpect, same pattern as test_keyboard.py.
"""
import platform
import sys
from pathlib import Path

import pytest

pexpect = pytest.importorskip("pexpect", reason="pexpect is POSIX-only")

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="raw_mode()'s POSIX branch (what these tests exercise) doesn't run on Windows",
)

PROBE = str(Path(__file__).resolve().parent / "_terminal_prompt_probe.py")
PYTHON = sys.executable


def spawn_probe():
    child = pexpect.spawn(PYTHON, [PROBE], timeout=5)
    child.expect("READY")
    return child


def test_backspace_erases_last_character():
    """Regression test for a fixed bug: only '\\b' (0x08, BS) was handled
    as backspace, but most real terminals (including this Pi over SSH)
    send '\\x7f' (0x7F, DEL) for the Backspace key -- pressing it did
    nothing, matching Colin's exact report ("backspace doesn't work in the
    interface").
    """
    child = spawn_probe()
    child.send("abc")
    child.send("\x7f")
    child.send("\r")
    child.expect("RESULT:.*")
    assert "'ab'" in child.after.decode()
    child.close(force=True)


def test_bs_control_char_also_erases_last_character():
    """The original '\\b' (BS) handling must keep working alongside the
    DEL fix -- some terminals/configurations do send BS."""
    child = spawn_probe()
    child.send("abc")
    child.send("\b")
    child.send("\r")
    child.expect("RESULT:.*")
    assert "'ab'" in child.after.decode()
    child.close(force=True)


def test_backspace_on_empty_input_does_not_error():
    child = spawn_probe()
    child.send("\x7f")
    child.send("a")
    child.send("\r")
    child.expect("RESULT:.*")
    assert "'a'" in child.after.decode()
    child.close(force=True)


def test_normal_typing_without_backspace():
    child = spawn_probe()
    child.send("hello")
    child.send("\r")
    child.expect("RESULT:.*")
    assert "'hello'" in child.after.decode()
    child.close(force=True)
