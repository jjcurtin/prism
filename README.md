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
