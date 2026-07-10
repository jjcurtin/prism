"""cross-platform non-blocking single-keypress reading, replacing msvcrt
(Windows-only stdlib) so the interface can run on Linux/Mac too."""

import sys
import os
import platform
import contextlib

IS_WINDOWS = platform.system() == 'Windows'

if IS_WINDOWS:
    import msvcrt
else:
    import termios
    import tty
    import select

    # os.read() on the raw fd, not sys.stdin.read() — sys.stdin is a
    # buffered TextIOWrapper, and select() only sees unread bytes at the OS
    # level. Reading through the buffered wrapper can silently pull extra
    # bytes (e.g. the rest of an arrow-key escape sequence) into Python's
    # internal buffer where select() can no longer see them, making the
    # next select() call falsely report "no data ready".
    #
    # Resolved lazily (not at import time): sys.stdin has no real fd when
    # this module is merely imported under redirected/non-tty stdin (e.g.
    # pytest's default capture, or a service with stdin from /dev/null) —
    # only kbhit()/getwch()/read_arrow_key() actually need a real terminal.
    def _stdin_fd():
        return sys.stdin.fileno()


@contextlib.contextmanager
def raw_mode():
    """Enables kbhit()/getwch() for the duration of the block. No-op on
    Windows (msvcrt already reads the console raw per-call). On POSIX,
    puts stdin into cbreak mode and always restores the original settings
    on exit, including on exception — raw mode is process-global tty state
    and must not leak past the interactive prompt that needed it.
    """
    if IS_WINDOWS:
        yield
        return
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def kbhit():
    """Non-blocking check for whether a key is waiting to be read."""
    if IS_WINDOWS:
        return msvcrt.kbhit()
    dr, _, _ = select.select([_stdin_fd()], [], [], 0)
    return bool(dr)


def getwch():
    """Blocking read of exactly one raw character. Call only after
    kbhit() returns True (and, on POSIX, within a raw_mode() block)."""
    if IS_WINDOWS:
        return msvcrt.getwch()
    return os.read(_stdin_fd(), 1).decode(errors='replace')


# Arrow keys arrive as a different byte sequence per platform: Windows
# sends a '\x00'/'\xe0' prefix followed by one letter (getwch() twice);
# POSIX sends the ANSI escape '\x1b' '[' followed by one letter (three
# reads). read_arrow_key() normalizes both into the same small set of
# direction strings so callers don't need platform branches of their own.
_WINDOWS_ARROW_MAP = {'H': 'UP', 'P': 'DOWN', 'K': 'LEFT', 'M': 'RIGHT'}
_POSIX_ARROW_MAP = {'A': 'UP', 'B': 'DOWN', 'D': 'LEFT', 'C': 'RIGHT'}


def read_arrow_key(first_char):
    """Given a char just read via getwch() that might be the start of an
    arrow-key sequence, consumes the rest of that sequence (if any) and
    returns 'UP'/'DOWN'/'LEFT'/'RIGHT', or None if first_char wasn't the
    start of one (nothing extra is consumed in that case)."""
    if IS_WINDOWS:
        if first_char not in ('\x00', '\xe0'):
            return None
        return _WINDOWS_ARROW_MAP.get(getwch())
    if first_char != '\x1b':
        return None
    # a short wait distinguishes a real escape sequence from a lone ESC
    # keypress, without blocking indefinitely on the latter.
    if not select.select([_stdin_fd()], [], [], 0.05)[0]:
        return None
    if getwch() != '[':
        return None
    if not select.select([_stdin_fd()], [], [], 0.05)[0]:
        return None
    return _POSIX_ARROW_MAP.get(getwch())
