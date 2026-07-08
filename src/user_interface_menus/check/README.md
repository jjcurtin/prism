# System Status and Diagnostics

Reached from the Main Menu with `check`. Use this when you want to confirm
PRISM is actually running before you report a problem, or after making a
change you want to sanity-check.

## What you'll see

Every time you open this menu it shows:

- **Mode** — what mode the server is running in
- **Uptime** — how long PRISM has been running since it was last started

If it instead prints `PRISM not running or inaccessible.`, the server isn't
reachable from this interface — let your PRISM administrator know.

## Running diagnostics

Type `diagnostics` to have PRISM run its internal system check (verifying
packages, folders, required files, API connectivity, and participant data).

- **Success** prints `System checks complete. No issues found.`
- **Failure** prints the last 25 lines of the transcript so you (or whoever
  you escalate to) can see what went wrong — see `logs/README.md` if you
  want to look at more than that.
