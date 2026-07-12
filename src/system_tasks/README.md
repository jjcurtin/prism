# System Tasks

The individual background jobs PRISM can run — either on a schedule (see
`config/system_task_schedule.csv` and the `tasks` menu) or on demand. Each
task type shows up by name in the `tasks add system` / `tasks execute`
menus (see `src/user_interface_menus/tasks/README.md`).

## What each task type does

- **`CHECK_SYSTEM`** — the "run diagnostics" task behind the `check` menu.
  Verifies the folder layout, the research-drive connection, and the
  participant roster (duplicate IDs).
- **`RUN_R_SCRIPT`** — runs a single R script. Any script placed in the
  repo's `scripts/` folder is automatically picked up and offered as a
  choice in the `tasks add rscript` menu — you don't need to register it
  anywhere.

If a scheduled task fails, whoever is on `config/study_coordinators.csv`
gets a text about it (in live mode).

## Adding a new task type (for whoever maintains PRISM's code)

Task types are **statically registered**, not auto-discovered — there's no
filesystem-listing/dynamic-import mechanism, so adding one means updating a
registry by hand:

- Create a new file directly in this folder: lowercase, underscore-
  separated, with a leading underscore (`_my_new_task.py`).
- Inside it, define a class matching the filename in `TitleCase` (e.g.
  `_check_system.py` → `CheckSystem`) that subclasses `SystemTask` and
  implements `run()`, returning `0` on success and non-zero on failure.
  `run()` must also set `self.task_type` (e.g.
  `self.task_type = "CHECK_SYSTEM"`) — that string is what
  `config/system_task_schedule.csv` and the `tasks` menu use to refer to it.
- Import the class and add a `task_type: ClassName` line to the
  `TASK_CLASSES` dict in `../task_managers/_system_task_manager.py` — that
  dict is the single source of truth for which task types exist. A new task
  file has no effect until it's registered there, and becomes available on
  the next PRISM restart (no hot-reload).
