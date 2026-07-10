# System Tasks

The individual background jobs PRISM can run — either on a schedule (see
`config/system_task_schedule.csv` and the `tasks` menu) or on demand. Each
task type shows up by name in the `tasks add system` / `tasks execute`
menus (see `src/user_interface_menus/tasks/README.md`).

## What each task type does

- **`CHECK_SYSTEM`** — the "run diagnostics" task behind the `check` menu.
  Verifies the folder layout, connectivity to Qualtrics/FollowMee, the
  research-drive connection, and the participant roster (duplicate IDs).
- **`PULLDOWN_QUALTRICS_DATA`** — downloads the latest EMA and feedback
  survey responses from Qualtrics and writes cleaned CSVs into
  `../../data/qualtrics/`.
- **`PULLDOWN_FOLLOWMEE_DATA`** — downloads the latest GPS/location data
  from FollowMee and writes it into `../../data/followmee/`.
- **`RUN_R_SCRIPT`** — runs a single R script. Any script placed in the
  repo's `scripts/` folder is automatically picked up and offered as a
  choice in the `tasks add rscript` menu — you don't need to register it
  anywhere.
- **`RUN_R_SCRIPT_PIPELINE`** *(deprecated path)* — runs every enabled
  script listed in `config/script_pipeline.csv` in sequence. Prefer
  scheduling individual scripts via `RUN_R_SCRIPT` instead.

If a scheduled task fails, whoever is on `config/study_coordinators.csv`
gets a text about it (in prod mode).

## Adding a new task type (for whoever maintains PRISM's code)

New task types are picked up automatically — there's no registry to update
by hand:

- Create a new file directly in this folder: lowercase, underscore-
  separated, with a leading underscore (`_my_new_task.py`).
- Inside it, define a class matching the filename in `TitleCase` (e.g.
  `_check_system.py` → `CheckSystem`) that subclasses `SystemTask` and
  implements `run()`, returning `0` on success and non-zero on failure.
  `run()` must also set `self.task_type` (e.g.
  `self.task_type = "CHECK_SYSTEM"`) — that string is what
  `config/system_task_schedule.csv` and the `tasks` menu use to refer to it.
- PRISM reloads this folder every time the task list is requested and
  before each scheduled task runs, so new/edited task files take effect
  without restarting the server.
