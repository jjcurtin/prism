# Data

Where PRISM writes everything it pulls down from external services while a
study is running. Nothing here is tracked by git — it's all
participant/study data, generated automatically, not something you'll
usually touch by hand. This folder is empty until PRISM actually runs its
data-pulldown tasks (see `tasks` in the interface, or `src/system_tasks/README.md`).

## qualtrics/
Survey response data pulled down from Qualtrics.

- `raw/` — the untouched exports as downloaded (`raw_qualtrics_ema_data.csv`,
  `raw_qualtrics_feedback_data.csv`).
- `processed/` — the same data after PRISM cleans it up (removes header
  clutter, drops empty columns, filters already-submitted rows):
  `filtered_qualtrics_ema_data.csv`, `filtered_qualtrics_feedback_data.csv`.

## followmee/
GPS/location tracking data pulled from FollowMee (if the study uses location
tracking devices).

- `raw/` — the device list and the raw location history as returned by the
  FollowMee API (`followmee_device_list.json`, `raw_followmee_data.json`).
- `processed/` — one CSV per tracking device, appended to over time
  (`{device_id}_processed_followmee_data.csv`).

## messages/
Reserved for message/communication logs. Not currently written to by
anything in this version of PRISM — SMS is sent live via Twilio without
keeping a local copy here, so don't expect anything to show up in this
subfolder yet.

## What happens to this data

`tasks` can push everything under this folder out to the lab's research
drive (see the "push to research drive" system task), and the `check`
menu's diagnostics touch this folder as part of confirming PRISM's overall
health. There's currently no automatic cleanup — files accumulate here for
as long as the study runs, so periodically archiving `data/` (after
confirming a research-drive push succeeded) is worth doing on a long study.
