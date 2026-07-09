import os
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / 'src'
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# user_interface_menus/utils/_keyboard.py does `sys.stdin.fileno()` at
# *import* time (module load, POSIX branch) to get a raw fd for
# select()/os.read() later. Under plain `pytest` (no `-s`), pytest's
# capture manager replaces sys.stdin with a captured pseudo-file that has
# no real fileno() and raises `io.UnsupportedOperation` -- which would
# otherwise blow up at collection time for every test module in this
# directory that imports anything from user_interface_menus (the whole
# tree pulls in _display.py -> _keyboard.py). Give it a real,
# harmless fd instead; nothing in this test suite performs real keyboard
# I/O (test_keyboard.py drives a PTY via pexpect in a subprocess, which
# gets its own real stdin and never touches this one).
try:
    sys.stdin.fileno()
except Exception:
    sys.stdin = open(os.devnull, 'r')

import queue
from collections import deque

import pytest


class FakeInterface:
    """A lightweight stand-in for a real `PRISMInterface` instance (see
    src/prism_interface.py), for testing user_interface_menus/utils/ menu
    dispatch/fuzzy-search logic without a real terminal or network
    connection.

    Mirrors the attributes menu-dispatch code actually reads/writes:
    - `inputs_queue` (queue.Queue): pre-populate via `.put(...)` so
      `get_input`/`prompt_confirmation` take the queue-override path
      instead of blocking on real stdin.
    - `commands_queue` (collections.deque): chained/macro commands land
      here (see `CommandInjector`).
    - `debug` (bool): gates verbose prints in `_display.py`.
    - `api(method, endpoint, json=None)`: records calls instead of hitting
      a real network; returns None like a failed/unreachable request would.
    - `window_N_x`/`window_N_y`/`column_width`/`window_height`/
      `num_columns`: set dynamically by `print_key_line` in
      `_menu_display.py`; pre-seeded here so code that reads them before
      writing (e.g. `clear_assistant_area`) doesn't blow up on AttributeError.
    """

    def __init__(self):
        self.inputs_queue = queue.Queue()
        self.commands_queue = deque()
        self.debug = False
        self.api_calls = []
        for i in range(3):
            setattr(self, f'window_{i}_x', 0)
            setattr(self, f'window_{i}_y', 0)
        self.column_width = 10
        self.window_height = 1
        self.num_columns = 1

    def api(self, method, endpoint, json=None):
        self.api_calls.append((method, endpoint, json))
        return None


@pytest.fixture
def fake_interface():
    return FakeInterface()


@pytest.fixture(autouse=True)
def _menu_helper_state(monkeypatch):
    """`_menu_helper.py` holds several module-level globals that
    `_menu_navigation.py`/`_menu_display.py`/`_commands.py` read directly
    (not passed as parameters): the global command registry
    (`_menu_options`), fuzzy-match thresholds, `MENU_DELAY`
    (`goto_menu`/`process_chained_command` `time.sleep()` on this - real
    default is 0.5s), `COLOR_ON` (gates some, but not all, of the
    interactive-terminal codepaths), and `RECENT_COMMANDS`. Reset around
    every test via monkeypatch (auto-reverted at teardown) so tests can't
    leak global state into each other, and so the suite runs fast.
    """
    import user_interface_menus._menu_helper as _menu_helper

    monkeypatch.setattr(_menu_helper, '_menu_options', None)
    monkeypatch.setattr(_menu_helper, 'RELATED_OPTIONS_THRESHOLD', 0.3)
    monkeypatch.setattr(_menu_helper, 'BEST_OPTIONS_THRESHOLD', 0.7)
    monkeypatch.setattr(_menu_helper, 'MENU_DELAY', 0)
    monkeypatch.setattr(_menu_helper, 'COLOR_ON', False)
    monkeypatch.setattr(_menu_helper, 'RECENT_COMMANDS', [])
    monkeypatch.setattr(_menu_helper, 'local_menu_options', {})
    monkeypatch.setattr(_menu_helper, 'current_menu', None)

    # Safety net: some error paths (e.g. error()/success() -> exit_menu())
    # call the builtin input() directly. Never let that block the suite on
    # real stdin -- tests that care about get_input's queue-override path
    # pre-populate inputs_queue instead, per the CLI's own automation
    # pattern (see CommandInjector/process_chained_command).
    monkeypatch.setattr('builtins.input', lambda *a, **k: '')

    yield
