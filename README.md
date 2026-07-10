# PRISM

PRISM is a Flask-based backend that runs a behavioral-health research study: it
schedules and sends daily surveys to participants over SMS (delivered as a
bare Qualtrics survey link, with no PRISM-side page personalization), pulls
down survey/GPS data, and gives research staff a terminal UI
(`src/prism_interface.py`) to manage participants and background tasks.

## Navigating this repo

- **api/** *(git-ignored, created at runtime)* — plaintext API credential CSVs
  (Qualtrics, FollowMee, Twilio, the research drive). Not present in a
  fresh checkout; see `help ra start` in the interface for what's required.
- **config/** — configuration CSVs PRISM needs to run (participant roster,
  task schedule, coordinator list). See `config/README.md`.
- **data/** — output for pulled-down Qualtrics/FollowMee data. See
  `data/README.md`.
- **logs/** — transcripts and activity logs. See `logs/README.md`.
- **scripts/** *(git-ignored, created at runtime)* — R scripts for the script
  pipeline; auto-detected by the task system.
- **src/** — the PRISM server, interface, and system tasks. See
  `src/README.md`, which links onward to each subfolder's own README
  (`system_tasks/`, `task_managers/`, `user_interface_menus/` and its 8
  submenus).

## Security model

The Flask server (`src/run_prism.py`) binds to `127.0.0.1` only — it is not
reachable over the network, and the only client that talks to it
(`src/prism_interface.py`) is hardcoded to `http://localhost:5000/`. Given
that, none of its ~24 routes (`src/_routes.py`) require authentication: any
process or user account on the same machine can reach every route
unauthenticated, including `POST /system/shutdown` (hard exit) and R-script
execution. This was a deliberate, discussed tradeoff — not an oversight —
made because loopback-only binding already rules out network exposure;
per-process/per-user auth on a single-operator research machine was judged
not worth the added complexity right now. Revisit if the deployment model
ever changes (e.g. multi-user machine, network exposure).

## Documentation conventions

Every folder in this repo has two docs, kept deliberately separate:

- **`README.md`** (tracked) — a plain-English explanation of what the code in
  that folder does, aimed at research assistants and other human readers.
- **`CLAUDE.md`** (git-ignored — see `.gitignore`) — a technical/architectural
  write-up per folder (what it does under the hood, and known issues/what
  needs fixing). This is local working documentation, not part of the
  project's tracked history.

## Changelist

### In progress
- Error handling / input validation / exception surfacing audit across the
  whole app (routes, task managers, system tasks, server bootstrap, and the
  interface client) — several real bugs found and fixed so far this pass
  (an unhandled crash in two schedule-lookup endpoints, an SMS notifier that
  only ever alerted the first study coordinator, a research-drive push
  whose failures were reported as success, missing JSON-body validation on
  5 routes, and more); a handful of higher-risk findings that touch
  HTTP/return-value contracts are being tracked separately pending
  confirmation before changing. *(2026-07-09)*

### Completed
- Documented the server's trust model explicitly (see "Security model"
  above): loopback-only binding, no authentication on any route, a
  deliberate/discussed tradeoff rather than an oversight, not a gap to fix
  reflexively. *(2026-07-10)*
- Added the previously CI-excluded `tests/test_check_system.py` to
  `.github/workflows/tests.yml` as a new `system-checks` job. *(2026-07-10)*
- Research-drive sync now assumes the drive is already mounted (no more
  `net use`/plaintext-password `os.system()` mapping step) and copies
  cross-platform (`robocopy` on Windows, `rsync` on Linux) via `subprocess.run`
  argument lists instead of shell strings. Added integration tests
  (`tests_integration/`, local-only, real dev credentials, `make
  test-integration`) for the previously-untested pulldown/research-drive
  tasks. `uiconfig.txt`/`saved_macros.txt`/`system_prompt.txt` are now
  tracked in `config/` (copied from the prod drive) instead of git-ignored,
  so a fresh clone no longer needs to fetch them from the drive before the
  interface will start. *(2026-07-10)*
- Cross-platform port: server and interface now run on Linux (previously
  Windows-only — hard-coded paths centralized, the Windows-only `msvcrt`
  keypress module replaced with a `platform.system()`-branched
  `_keyboard.py`, a busy-wait CPU bug fixed). *(2026-07-09)*
- Automated test suite: 546 tests total — 147 server-side (`tests/`, config
  loading, task scheduling, participant management) and 399 interface-side
  (`tests_interface/`, full `user_interface_menus/` coverage). Runs via
  `make test-server` / `make test-client` / `make test-all`, with GitHub
  Actions CI split into semantically-grouped jobs per side. *(2026-07-10)*
- Cleaned up loose ends from the local-only-server audit: documented the
  deliberate no-auth trust model, closed a CI gap where two server-side test
  files ran locally but not in CI, replaced an ambiguous-`None` error
  contract (`prism_interface.py::api()`, `run_prism.py::get_transcript()`,
  and the routes that consume them) with explicit `(ok, data)` tuples,
  removed the dead EMA/feedback log reader (routes/menu/tests) left behind
  by the earlier Qualtrics-route removal, and dropped the long-dead
  `check_installed_packages()` stub in favor of a `check_tests()` health
  check that runs the offline suite. Also removed the research-drive-push
  system task (`PushDataToResearchDrive`) entirely — the plaintext-credential
  auto-mount it depended on was already dropped for security reasons, the
  task was unscheduled in both `dev` and `prod`, and the drive-side
  `research_drive.api` config it read was confirmed intentionally deleted.
  Added an integration test (`tests_integration/test_environment_files.py`)
  that checks required config files exist and are filled in (not just
  template placeholders) for both the `dev` and `prod` drive environments.
  *(2026-07-10)*
- Added README.md docs for the entire `src/user_interface_menus/` menu tree
  (main menu + assistant/check/help/logs/participants/settings/tasks/utils),
  paired with each folder's existing CLAUDE.md. *(2026-07-08)*
- Rewrote the pre-existing README.md files (`config/`, `data/`, `logs/`,
  `qualtrics_js/`, `src/`, `src/system_tasks/`, `src/task_managers/`) to match
  the same plain-English depth. *(2026-07-08)*
- Removed 83 previously git-tracked `__pycache__/*.pyc` files; `.gitignore`
  now excludes `__pycache__/` and `*.pyc` going forward. *(commit `8776d95`)*
- `.gitignore` now excludes `CLAUDE.md` at every depth, so per-folder
  technical notes stay local instead of landing in shared history.
  *(2026-07-08)*

### Planned
Pulled from the per-folder CLAUDE.md "Improvements" notes and this
session's error-handling audit — see those files for full detail:
- Close the open SMS relay (unvalidated participant/announcement endpoints
  can trigger real Twilio sends).
