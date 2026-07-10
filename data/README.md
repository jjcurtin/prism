# Data

Where PRISM would write output pulled down from external services while a
study is running. Nothing here is tracked by git. Currently unused: the
data-pulldown tasks that used to write here (Qualtrics survey responses,
FollowMee location data) were both removed entirely — PRISM does not pull
down or store any Qualtrics survey response data; surveys are still sent to
participants, just as a bare link (see root `README.md`). This folder is
kept in case a future task needs a repo-root-relative data directory again
(see `run_prism.py`'s `data_dir`).

## messages/
Reserved for message/communication logs. Not currently written to by
anything in this version of PRISM — SMS is sent live via Twilio without
keeping a local copy here, so don't expect anything to show up in this
subfolder yet.

## What happens to this data

The `check` menu's diagnostics touch this folder as part of confirming
PRISM's overall health. There's currently no automatic cleanup — files
accumulate here for as long as the study runs, so periodically archiving
`data/` is worth doing on a long study.
