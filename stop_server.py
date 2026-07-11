"""Stops a running PRISM server.

Prefers the PID file run_prism.py writes on startup (repo_root/
.run_prism.pid, see PID_FILE_NAME in src/run_prism.py) -- a precise,
PID-targeted kill. If no PID file is present (e.g. an already-running
server started before this feature existed, or the write itself
failed), falls back to a pattern match against "run_prism.py" in every
process's command line -- but, since an external adversarial review
demonstrated this fallback killing unrelated bystander processes live
(four separate times, including the operator's own shell -- any process
whose command line merely contains that substring matches: a second
checkout's server, `vim run_prism.py`, a grep), the fallback no longer
kills anything itself. It lists the matching candidates and tells the
operator to verify and kill the right one manually. As of
src/run_prism.py's _acquire_pid_file (refuses a second launch while a
live instance still holds the PID file), a live PRISM instance should
essentially always have a PID file naming it -- the fallback's only
real remaining trigger is "no PID file at all", not "an unstoppable
live instance", so killing blind here is no longer defensible.
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
        # Found by an external adversarial review: the old `finally:
        # PID_FILE.unlink(missing_ok=True)` ran on THIS path too (finally
        # always runs, including when the except body itself returns) --
        # so a failed kill attempt (e.g. PermissionError, if this script is
        # run as a different user than the one that started run_prism.py)
        # still deleted the PID file. The next launch would then see no
        # PID file, believe nothing was running, and start a second live
        # instance alongside the still-running first one -- silently
        # recreating the exact double-launch scenario _acquire_pid_file()
        # exists to prevent. Only unlink on an actual stop (the two
        # fallthrough paths below), never on this one.
        return False
    PID_FILE.unlink(missing_ok=True)
    return True


def _stop_via_pattern_match() -> bool:
    """Reports candidate processes instead of killing them -- see the
    module docstring for why. Returns True if at least one candidate was
    found and reported (caller should exit nonzero, since nothing was
    actually stopped and a human needs to look), False if none were found
    (nothing to do, a clean "no server running" outcome).
    """
    if sys.platform == "win32":
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_prism.py' } "
                "| ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }",
            ],
            check=False, capture_output=True, text=True,
        )
        candidates = [line for line in result.stdout.splitlines() if line.strip()]
    else:
        # pgrep -a prints "PID full-command-line" per match, one per line --
        # matches on the full argv, same substring the old pkill -f used.
        result = subprocess.run(
            ["pgrep", "-af", r"run_prism\.py"], check=False, capture_output=True, text=True,
        )
        candidates = [line for line in result.stdout.splitlines() if line.strip()]

    if not candidates:
        print("No PID file found, and no PRISM server process found by pattern match.")
        return False

    print(
        "No PID file found. NOT killing by pattern -- found these candidate "
        "processes; verify and kill the right one manually:"
    )
    for line in candidates:
        pid = line.split(maxsplit=1)[0]
        print(f"  kill {pid}   # {line}")
    return True


def main() -> int:
    if _stop_via_pid_file():
        time.sleep(1)
        return 0
    found_candidates = _stop_via_pattern_match()
    time.sleep(1)
    return 1 if found_candidates else 0


if __name__ == "__main__":
    sys.exit(main())
