# Config

**Updated 2026-07-09 — config/api are now sourced from the research drive,
not this folder.** `run_prism.py`'s `load_paths()`/`load_api_keys()` read
`S:/optimize/prism/<environment>/` (`<environment>` from the git-ignored
`environment` marker file at the repo root, `dev` or `prod`) for everything
study-specific: the `api/` folder (Qualtrics/FollowMee/Twilio/etc. credentials
+ SMS message text), and most of `config/` (`study_coordinators.csv`,
`system_task_schedule.csv`, `script_pipeline.csv`, `followmee_coords.csv`).
`study_participants.csv`/`reminders.csv` live under a separate
`data_raw/participants/` path on the same drive (`dev_`-prefixed for the dev
environment), per that environment's `paths.csv`. On Linux, the drive mounts
at `/mnt/research_drive` (WiscVPN + CIFS — see `research-drive-map`/
`wisc-connect` aliases); on Windows it's the mapped `S:` drive directly.

This folder now only holds two things:
- `repo_paths.csv` — **tracked**, unlike everything else here. Internal
  resolution facts for this repo checkout itself (where logs live locally,
  how the drive mounts per-platform, which drive subpath this project is
  under) — as opposed to study-specific data, which comes from the drive.
- Nothing else — no local `.template`/placeholder files anymore. Removed
  2026-07-09: `PRISM.__init__` now depends on `config_base` (drive-sourced)
  regardless of dev/prod, so local placeholders no longer serve a
  boot-without-the-drive purpose the way they briefly did during initial
  Linux port work — the drive is the single source of truth.

## Current known schema (from the real files on the drive)

`study_participants.csv`: `initials,subid,unique_id,on_study,phone_number,ema_time,ema_reminder_time,feedback_time,feedback_reminder_time`.
Note `_participant_manager.py` has an unfinished migration to this schema —
see the code comment near its CSV-parsing logic — flagged, not yet fixed.

`reminders.csv`: `subid,unique_id,on_study,remind_ema,remind_feedback`.

`study_coordinators.csv`: `name,phone_number` (10 digits) — who gets texted
if a background task or system check fails.

`system_task_schedule.csv`: `task_type,task_time,r_script_path,run_today` —
`task_type` must match a task class in `src/system_tasks/`.

`script_pipeline.csv` *(deprecated)*: `script_path,arguments,enabled` — an
older mechanism for chaining R scripts. Prefer dropping scripts where
`r_scripts_dir` points, which PRISM auto-detects.

## A note on editing these by hand

You *can* edit these CSVs directly, but it's safer to make changes through
the `prism_interface.py` menus where possible (`participants`, `tasks`) —
the interface validates formats (phone numbers, times, IDs) before writing,
whereas a hand-edited CSV with a typo (wrong time format, missing column)
can fail silently at runtime. If you do edit a file directly while PRISM is
running, use `participants refresh` afterward to reload it.
