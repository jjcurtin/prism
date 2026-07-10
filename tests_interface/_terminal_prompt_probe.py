"""Standalone helper spawned via pexpect (needs a real PTY for raw_mode()
cbreak-mode reading) -- drives print_fixed_terminal_prompt() with a minimal
fake `self` and prints the final recovered string, so a driving test can
assert on real keypress-editing behavior (e.g. backspace) rather than
poking internals."""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / 'src'
sys.path.insert(0, str(SRC_DIR))

import user_interface_menus._menu_helper as menu_helper
from user_interface_menus.utils._display import print_fixed_terminal_prompt

# avoid syntax_highlight_string's get_cursor_position() ANSI query, which
# blocks forever waiting for a response a plain PTY child won't send.
menu_helper.ui_state.color_on = False


class FakeSelf:
    debug = False


print("READY", flush=True)
result = print_fixed_terminal_prompt(FakeSelf(), submenu=True)
print(f"RESULT:{result!r}", flush=True)
