# PRISM

PRISM is a Flask-based backend that runs a behavioral-health research study: it
schedules and sends daily surveys to participants over SMS (delivered as a
bare Qualtrics survey link, with no PRISM-side page personalization) and
gives research staff a terminal UI (`src/prism_interface.py`) to manage
participants and background tasks.

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
RA terminal interface), `test server` / `test client` / `test
integration` / `test all` (run the pytest suites described below), and
`typecheck` (run mypy over `src/`; see `mypy.ini` -- gradual/non-strict,
`src/` only, wired into CI as its own job).

## Navigating this repo

- **api/** *(git-ignored, created at runtime)* — plaintext API credential CSVs
  (Qualtrics, Twilio, the research drive). Not present in a
  fresh checkout; sourced from the research drive, see `config/README.md`
  for what's required.
- **config/** — configuration CSVs PRISM needs to run (participant roster,
  task schedule, coordinator list). See `config/README.md`.
- **data/** — currently unused (the data-pulldown tasks that used to write
  here were removed; PRISM does not pull down or store any Qualtrics survey
  data). See `data/README.md`.
- **logs/** — transcripts and activity logs. See `logs/README.md`.
- **scripts/** *(git-ignored, created at runtime)* — R scripts for the script
  pipeline; auto-detected by the task system.
- **src/** — the PRISM server, interface, and system tasks. See
  `src/README.md`, which links onward to each subfolder's own README
  (`system_tasks/`, `task_managers/`, `user_interface_menus/` and its 6
  submenus).
