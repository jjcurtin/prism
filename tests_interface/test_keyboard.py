"""Tests for _keyboard.py, the phase-03 cross-platform keypress module.

Needs a real PTY — termios/tty cbreak mode (and non-blocking select()
polling) don't work over a plain pipe, only a real or pseudo terminal — so
these spawn the module under pexpect rather than importing it directly.
pexpect itself doesn't support Windows, and _keyboard.py's POSIX branch
(what these tests exercise) doesn't run there either — skipped on Windows
rather than silently passing nothing. The Windows branch (msvcrt) is a
known, documented, untested gap (see plan/04-interface-pytest.md) — there's
no Windows machine available to verify it directly.
"""
import platform
import sys
from pathlib import Path

import pytest

pexpect = pytest.importorskip("pexpect", reason="pexpect is POSIX-only")

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="_keyboard.py's POSIX branch (what these tests exercise) doesn't run on Windows",
)

PROBE = str(Path(__file__).resolve().parent / "_keyboard_probe.py")
PYTHON = sys.executable


def spawn_probe(key_count):
    child = pexpect.spawn(PYTHON, [PROBE, str(key_count)], timeout=5)
    child.expect("READY")
    return child


def test_kbhit_false_when_no_key_waiting():
    child = spawn_probe(1)
    # nothing sent yet — the probe should still be waiting, not have
    # reported a (spurious) keypress
    with pytest.raises(pexpect.TIMEOUT):
        child.expect("KEY:|ARROW:", timeout=0.3)
    child.close(force=True)


def test_normal_key_identified_correctly():
    child = spawn_probe(1)
    child.send("a")
    child.expect("KEY:'a'")
    child.expect("DONE")
    child.close(force=True)


@pytest.mark.parametrize("escape_seq,expected", [
    ("\x1b[A", "UP"),
    ("\x1b[B", "DOWN"),
    ("\x1b[C", "RIGHT"),
    ("\x1b[D", "LEFT"),
])
def test_arrow_keys_identified_correctly(escape_seq, expected):
    child = spawn_probe(1)
    child.send(escape_seq)
    child.expect(f"ARROW:{expected}")
    child.expect("DONE")
    child.close(force=True)


def test_lone_escape_keypress_does_not_hang_or_misfire():
    # a bare ESC (no following '[' + letter) must not be misidentified as
    # an arrow key, and must not block waiting for bytes that never come
    child = spawn_probe(1)
    child.send("\x1b")
    child.expect("KEY:'\\\\x1b'")
    child.expect("DONE")
    child.close(force=True)


def test_multiple_keys_read_in_order():
    child = spawn_probe(3)
    child.send("x")
    child.send("\x1b[A")
    child.send("y")
    child.expect("KEY:'x'")
    child.expect("ARROW:UP")
    child.expect("KEY:'y'")
    child.expect("DONE")
    child.close(force=True)
