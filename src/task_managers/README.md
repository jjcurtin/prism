# Task Managers

The scheduling engine running behind PRISM's server — this is what actually
decides "it's 4pm, time to text this participant their EMA survey" or
"it's midnight, time to run the data pulldown." RAs don't interact with this
folder directly; it's what powers the `tasks` and `participants` menus.

## How it works

- There are two task managers, each running on its own background thread so
  they don't block each other or the server:
  - **`SystemTaskManager`** — runs the jobs in `../system_tasks/` (data
    pulldowns, health checks, R scripts) on the schedule in
    `config/system_task_schedule.csv`.
  - **`ParticipantManager`** — owns the participant roster
    (`config/study_participants.csv`) and schedules each participant's daily
    EMA/feedback/reminder texts based on their individual times.
- Both check once a second for anything due, and use a first-in-first-out
  queue — so if several things are due at once, they run in the order they
  were queued rather than all at once.
- Both share the same underlying base class (add/remove a task, check
  what's due), and each adds its own specific behavior on top (e.g. the
  participant manager also knows how to send SMS; the system task manager
  knows how to dynamically load a task class by name).

## Why this matters day to day

If a survey text didn't go out, or a scheduled task didn't run, this is the
layer responsible — the `logs` menu's transcript view is the best way to
see what these managers actually did (or failed to do) around the time in
question.
