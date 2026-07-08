# Manage System Tasks / R Scripts

Reached from the Main Menu with `tasks`. This is where you schedule
background work for PRISM — built-in system tasks (like pulling down
survey data) as well as R scripts.

Opening this menu always shows the current schedule first: each entry's
number, task type (or script), scheduled time, and whether it's set to run
today.

## Options

- `add` — schedule a new task:
  - `system` — pick from PRISM's built-in task types and give it a time
    (`HH:MM:SS`)
  - `rscript` — pick an R script (anything placed in the `scripts` folder
    is detected automatically) and give it a time
  - Leaving the time blank, or typing it in the wrong format, schedules it
    for `00:00:00` instead — PRISM will tell you this happened.
- `remove` — remove a scheduled task by its number in the printed schedule
- `execute` — run a task or R script right now, instead of waiting for its
  scheduled time (same `system` / `rscript` choice as `add`)
- `clear` — wipe the entire task schedule (asks for confirmation first —
  this can't be undone)

## Tips

- The number you use with `remove` refers to that task's position in the
  schedule as printed *right now* — if the schedule changes, re-check it
  before removing by number.
- `execute` runs something immediately without adding it to the schedule;
  use `add` if you want it to happen automatically going forward.
