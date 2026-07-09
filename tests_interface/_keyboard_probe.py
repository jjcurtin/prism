"""Standalone helper spawned via pexpect (needs a real PTY for termios/
cbreak mode to work) — reads N keypresses and prints one line per result,
so a driving test can assert on stdout rather than poking internals."""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / 'src'
sys.path.insert(0, str(SRC_DIR))

from user_interface_menus.utils import _keyboard as kb

count = int(sys.argv[1]) if len(sys.argv) > 1 else 1

print("READY", flush=True)
with kb.raw_mode():
    seen = 0
    while seen < count:
        if kb.kbhit():
            ch = kb.getwch()
            arrow = kb.read_arrow_key(ch)
            if arrow:
                print(f"ARROW:{arrow}", flush=True)
            else:
                print(f"KEY:{ch!r}", flush=True)
            seen += 1
print("DONE", flush=True)
