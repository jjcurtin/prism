"""Stops a running PRISM server.

Prefers the PID file run_prism.py writes on startup (repo_root/
.run_prism.pid, see PID_FILE_NAME in src/run_prism.py) -- a precise,
PID-targeted kill instead of the old `pkill -f run_prism.py` pattern
match, which would also kill any unrelated process whose command line
merely contained that string (a second checkout's server, `vim
run_prism.py`, a grep). Falls back to the old pattern-matching approach
if no PID file is present (e.g. an already-running server started
before this change, or the write itself failed) -- a strict PID-only
version would otherwise leave that process unstoppable by this script
until it's killed manually once.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PID_FILE = Path(__file__).resolve().parent / '.run_prism.pid'


def _stop_via_pid_file() -> bool:
    """Returns True if a PID file was found and acted on (kill attempted
    or the process was already gone) -- False means "no PID file, caller
    should fall back", not "stopping failed".
    """
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass  # already dead -- still a successful "stop"
    except OSError:
        return False
    finally:
        PID_FILE.unlink(missing_ok=True)
    return True


def _stop_via_pattern_match() -> None:
    if sys.platform == "win32":
        subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_prism.py' } "
                "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }",
            ],
            check=False,
        )
    else:
        subprocess.run(["pkill", "-f", "run_prism.py"], check=False)


def main() -> None:
    if not _stop_via_pid_file():
        _stop_via_pattern_match()
    time.sleep(1)


if __name__ == "__main__":
    main()
