# Config

The CSV files PRISM reads at startup to know what to do — who's in the
study, when to text them, and what background tasks to run. Nothing in this
folder is tracked by git (it's all study-specific, hand-maintained data), so
these files need to exist on disk before PRISM will run correctly.

## Files PRISM expects here

### `study_participants.csv`
The participant roster — this is what the `participants` menu reads from and
writes back to (see `src/user_interface_menus/participants/README.md`). One
row per participant:

**Path status (2026-07-09):** on Windows this historically lived on the
`S:` research drive (`S:/optimize/data_raw/participants/study_participants.csv`),
not in this repo. `config/paths.api`'s `participants_path` currently
defaults to a local placeholder (`config/study_participants.csv`) purely so
the server can boot without that drive connected — this is a stand-in, not
the real data source. Linux has no drive-letter equivalent; `plan/06-research-drive-sync.md`
already scopes the mount mechanism (`mount -t cifs` against the WiscAD
share), but the actual local mount point on Linux hasn't been decided yet.
Don't treat the local placeholder as authoritative until `participants_path`
is repointed at the real mounted location once phase 6 lands.

| Column | Format |
|---|---|
| `unique_id` | any identifier (the interface expects a 9-digit number) |
| `last_name` / `first_name` | any |
| `on_study` | `yes` or `no` |
| `phone_number` | 10-digit phone number |
| `ema_time` | daily EMA survey send time, `HH:MM:SS` |
| `ema_reminder_time` | EMA reminder send time, `HH:MM:SS` |
| `feedback_time` | daily feedback survey send time, `HH:MM:SS` |
| `feedback_reminder_time` | feedback reminder send time, `HH:MM:SS` |

### `study_coordinators.csv`
Who gets a text if something breaks (a failed background task, a failed
system check). One row per coordinator: `name`, `phone_number` (10 digits).

### `system_task_schedule.csv`
The recurring background task schedule — what the `tasks` menu shows and
edits (see `src/user_interface_menus/tasks/README.md`).

| Column | Format |
|---|---|
| `task_type` | must match a task class in `src/system_tasks/` — see that folder's README for the naming rule |
| `task_time` | `HH:MM:SS` |
| `run_today` | `yes`/`no` — whether it's still due today |

### `script_pipeline.csv` *(deprecated)*
An older mechanism for chaining R scripts: `script_path` (relative to
`scripts/`), `arguments` (space-separated), `enabled` (boolean). Prefer
dropping scripts in `scripts/` directly, which PRISM auto-detects.

## A note on editing these by hand

You *can* edit these CSVs directly, but it's safer to make changes through
the `prism_interface.py` menus where possible (`participants`, `tasks`) —
the interface validates formats (phone numbers, times, IDs) before writing,
whereas a hand-edited CSV with a typo (wrong time format, missing column)
can fail silently at runtime. If you do edit a file directly while PRISM is
running, use `participants refresh` afterward to reload it.
