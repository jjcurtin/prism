# Config

**Updated 2026-07-09 — config/api are now sourced from the research drive,
not this folder.** `run_prism.py`'s `load_paths()`/`load_api_keys()` read
`S:/optimize/prism/<environment>/` (`<environment>` from the git-ignored
`environment` marker file at the repo root, `dev` or `prod`) for everything
study-specific: the `api/` folder (Qualtrics/FollowMee/Twilio/etc. credentials
+ SMS message text), and most of `config/` (`study_coordinators.csv`,
`system_task_schedule.csv`, `followmee_coords.csv`).
`study_participants.csv`/`reminders.csv` live under a separate
`data_raw/participants/` path on the same drive (`dev_`-prefixed for the dev
environment), per that environment's `paths.csv`. On Linux, the drive mounts
at `/mnt/research_drive` (WiscVPN + CIFS — see `research-drive-map`/
`wisc-connect` aliases); on Windows the research drive is **always** mapped
to `S:` (a fixed lab convention, not a per-machine setting) — that's why
`repo_paths.csv`'s `drive_mount_windows` value and the `S:/...` literals
baked directly into `run_prism.py` are the same constant; there's no
per-machine Windows drive-letter substitution to worry about.

This folder now holds three things, all **tracked** (unlike everything else
here, which is drive-sourced or git-ignored):
- `repo_paths.csv` — internal resolution facts for this repo checkout itself
  (where logs live locally, how the drive mounts per-platform, which drive
  subpath this project is under) — as opposed to study-specific data, which
  comes from the drive.
- `uiconfig.txt`, `saved_macros.txt` — interface defaults (display tunables,
  starter macros). These are generic, not study-specific or secret, so
  unlike the drive-sourced files they ship with the repo rather than
  requiring a fresh clone to copy them from the drive first. *(2026-07-10)*

## Current known schema (from the real files on the drive)

`study_participants.csv`: `initials,subid,unique_id,on_study,phone_number,ema_time,ema_reminder_time,feedback_time,feedback_reminder_time`.
`_participant_manager.py`'s CSV parsing matches this schema (fixed 2026-07-09,
commit `271b865`).

`reminders.csv`: `subid,unique_id,on_study,remind_ema,remind_feedback`.
`remind_ema`/`remind_feedback` are `"yes"`/`"no"` flags meaning "has this
participant already opened today's EMA/feedback survey" — `"yes"` means
`process_task()` skips that reminder send. Nothing in PRISM's own codebase
writes this file; it's populated by an external process (fixed 2026-07-10,
was previously read via wrong column names — see
`src/task_managers/CLAUDE.md`).

`study_coordinators.csv`: `name,phone_number` (10 digits) — who gets texted
if a background task or system check fails.

`system_task_schedule.csv`: `task_type,task_time,r_script_path,run_today` —
`task_type` must match a task class in `src/system_tasks/`.

`script_pipeline.csv` *(removed 2026-07-10)*: the older `RUN_R_SCRIPT_PIPELINE`
mechanism for chaining R scripts (and this CSV, and `self.script_pipeline_path`)
were removed entirely, not just deprecated. Drop scripts where `r_scripts_dir`
points instead — PRISM auto-detects them for the `RUN_R_SCRIPT` task.

## A note on editing these by hand

You *can* edit these CSVs directly, but it's safer to make changes through
the `prism_interface.py` menus where possible (`participants`, `tasks`) —
the interface validates formats (phone numbers, times, IDs) before writing,
whereas a hand-edited CSV with a typo (wrong time format, missing column)
can fail silently at runtime. If you do edit a file directly while PRISM is
running, use `participants refresh` afterward to reload it.
