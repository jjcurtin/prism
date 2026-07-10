# PRISM

PRISM is a Flask-based backend that runs a behavioral-health research study: it
schedules and sends daily surveys to participants over SMS (delivered as a
bare Qualtrics survey link, with no PRISM-side page personalization), pulls
down survey/GPS data, and gives research staff a terminal UI
(`src/prism_interface.py`) to manage participants and background tasks.

## Getting Started

`python tasks.py --help` is the canonical, cross-platform entry point for
every dev task (setup, running the server, running the interface, running
tests) -- it works the same on Windows (no `make` there) as on Linux/macOS.
Run `python tasks.py <command> --help` for a given command's own options.
On Linux/macOS, `make <target>` is a thin convenience wrapper around the
same commands; run `make` with no target for the same list. Available
commands: `setup` (create the venv and install dependencies -- run with the
system python, before the venv exists), `run --mode test` / `run --mode
prod` (stop any running server, then start PRISM in the given mode -- no
default mode, to avoid accidentally booting prod), `interface` (launch the
RA terminal interface), and `test server` / `test client` / `test
integration` / `test all` (run the pytest suites described below).

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
- Removed several obsolete features entirely: the PRISM Assistant (chat
  menu, Azure-backed `_prism_assistant.py`, `@`/`assistant `-prefix command
  routing, `ASSISTANT_TEMPERATURE`/`ASSISTANT_TOKENS` tunables, and
  `config/system_prompt.txt` — `ASSISTANT_TYPE_SPEED` and
  `assistant_header_write` stay, since they power the generic header-typing
  effect used elsewhere, not just assistant chat); the help-menu tree
  (`help`, `help ra`/research-assistant docs, `help dev`/developer docs —
  the startup README content itself, `read_me`/`README`/`read_me_lines`,
  moved into `_menu_helper.py` since `prism_interface.py` uses it directly
  on startup and it isn't help-menu-specific); the deprecated
  `RUN_R_SCRIPT_PIPELINE` task and `config/script_pipeline.csv` (the
  still-live single-script `RUN_R_SCRIPT` task is unaffected); and the
  Windows-only `src/check_loc.ps1`. Also moved the pulldown tasks'
  (`PulldownQualtricsData`, `PulldownFollowmeeData`) hardcoded
  `"../data/..."` path literals onto a new `self.app.data_dir`
  (`config/repo_paths.csv`, resolved the same way as `logs_dir`), removing
  their implicit dependency on a cwd of `src/`. *(2026-07-10)*
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
  tasks. `uiconfig.txt`/`system_prompt.txt` are now tracked in `config/`
  (copied from the prod drive) instead of git-ignored, so a fresh clone no
  longer needs to fetch them from the drive before the interface will
  start. *(2026-07-10)*
- Removed the macro subsystem (saved/named command-chain shortcuts via
  `$<id> = <chain>`, plus the pre-canned `system_tests.txt`/
  `system_utils.txt` shortcut files and the guided `register` menu) —
  command chaining (`/cmd1?input/cmd2`) and global command search (`?`)
  are unaffected; only saving/naming a chain for later reuse is gone.
  *(2026-07-10)*
- Extended coordinator SMS-on-system-failure coverage beyond
  `SystemTaskManager`-dispatched tasks (unchanged: still gated on
  `app.mode == "prod"`, still sends on both SUCCESS and FAILURE for those).
  Refactored the coordinator-list-reading/sending logic out of
  `SystemTask.notify_via_sms()` into a new shared `_helper.notify_coordinators(app,
  message)`, then wired it into three genuine-system-failure paths that
  previously had no coordinator alert at all: `SystemTaskManager.process_task()`'s
  dynamic-import/dispatch failure, `ParticipantManager.process_task()`'s
  SMS-send failures (also fixed a bug there — the outermost `except
  Exception` had no `return` statement, implicitly returning `None` instead
  of `-1`), and `TaskManager.run()`'s outer catch-all (shared by both
  managers' background threads). Also added a generic Flask
  `errorhandler(Exception)` in `_routes.py` for truly unhandled exceptions
  (500/502), which alerts coordinators and re-raises/passes through
  `HTTPException`s (404/405 routing errors) so those don't spuriously
  trigger it. *(2026-07-10)*
- Added a global `home` command to fix the recursive-menu-exit bug: backing
  out of N nested menus used to require N separate `ENTER` presses (each
  submenu runs its own dispatch loop as a directly nested Python call).
  `home` now unwinds the whole call stack back to the main menu in one
  step, via a `ReturnToMainMenu` exception (`utils/_menu_navigation.py`)
  that every blanket `except Exception` on the navigation path re-raises
  instead of swallowing, caught for real only in `_main_menu.py`'s
  `main_menu()`. *(2026-07-10)*
- Cross-platform port: server and interface now run on Linux (previously
  Windows-only — hard-coded paths centralized, the Windows-only `msvcrt`
  keypress module replaced with a `platform.system()`-branched
  `_keyboard.py`, a busy-wait CPU bug fixed). *(2026-07-09)*
- Automated test suite: 501 tests total — 164 server-side (`tests/`, config
  loading, task scheduling, participant management, coordinator SMS alerting
  on system failures) and 337 interface-side (`tests_interface/`, full
  `user_interface_menus/` coverage). Runs via `make test-server` / `make
  test-client` / `make test-all`, with GitHub Actions CI split into
  semantically-grouped jobs per side. *(2026-07-10)*
- Cleaned up loose ends from the local-only-server audit: documented the
  deliberate no-auth trust model, closed a CI gap where two server-side test
  files ran locally but not in CI, replaced an ambiguous-`None` error
  contract (`prism_interface.py::api()`, `run_prism.py::get_transcript()`,
  and the routes that consume them) with explicit `(ok, data)` tuples,
  removed the dead EMA/feedback log reader (routes/menu/tests) left behind
  by the earlier Qualtrics-route removal, and dropped the long-dead
  `check_installed_packages()` stub (the `check_tests()` replacement that
  briefly ran the offline suite from inside `CheckSystem` was itself
  removed the same day — CheckSystem shouldn't run the test suite). Also
  removed the research-drive-push
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
