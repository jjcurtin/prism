# PRISM

PRISM is a Flask-based backend that runs a behavioral-health research study: it
schedules and sends daily surveys to participants over SMS, serves the
Qualtrics survey pages that collect responses, pulls down survey/GPS data, and
gives research staff a terminal UI (`src/prism_interface.py`) to manage
participants and background tasks.

## Navigating this repo

- **api/** *(git-ignored, created at runtime)* — plaintext API credential CSVs
  (Qualtrics, FollowMee, Twilio, ngrok, the research drive). Not present in a
  fresh checkout; see `help ra start` in the interface for what's required.
- **config/** — configuration CSVs PRISM needs to run (participant roster,
  task schedule, coordinator list). See `config/README.md`.
- **data/** — output for pulled-down Qualtrics/FollowMee data. See
  `data/README.md`.
- **logs/** — transcripts and activity logs. See `logs/README.md`.
- **qualtrics_js/** — the JavaScript the Qualtrics survey pages use to talk to
  the PRISM server. See `qualtrics_js/README.md`.
- **scripts/** *(git-ignored, created at runtime)* — R scripts for the script
  pipeline; auto-detected by the task system.
- **src/** — the PRISM server, interface, and system tasks. See
  `src/README.md`, which links onward to each subfolder's own README
  (`system_tasks/`, `task_managers/`, `user_interface_menus/` and its 8
  submenus).

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
- Repo-wide documentation pass (this file): add/refresh the navigation guide
  above and this changelist. *(2026-07-08)*

### Completed
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
Pulled from the per-folder CLAUDE.md "Improvements" notes — see those files
for full detail:
- Add authentication to the Flask backend (every route is currently open,
  including shutdown and arbitrary R-script execution).
- Close the open SMS relay (unvalidated participant/announcement endpoints
  can trigger real Twilio sends).
- Fix command injection and plaintext-credential handling in the
  research-drive sync (`os.system()` calls building shell strings from
  plaintext passwords).
- Remove hard-coded Windows-only paths so the server can run cross-platform.
- Add an automated test suite (currently only a manual, macro-driven smoke
  test exists).