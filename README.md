# PRISM Help Manual

PRISM is a Flask-based backend that runs a behavioral-health research study:
it schedules and sends daily surveys to participants over SMS (delivered as
a bare Qualtrics survey link, with no PRISM-side page personalization) and
gives research staff a terminal UI (`prism_interface.py`) to manage
participants and background tasks.

This manual is the **single source of documentation for PRISM** — every
README.md that used to live in a subfolder of this repository has been
folded into this one file, organized by chapter. If you're looking for
something that used to be in `config/README.md`, `src/README.md`,
`src/user_interface_menus/participants/README.md`, or any other subfolder
README, it's here now.

It's written for research assistants (RAs) using and troubleshooting PRISM
day to day. You don't need to already know Python or the command line to
follow Chapters 1–3, just be comfortable copy-pasting commands into a
terminal. The appendices are more technical (file schemas, code layout) and
are aimed at whoever maintains PRISM's code, but are useful background for
any RA who wants to understand what's happening under the hood.

## Table of Contents

- [Chapter 1 — Getting Started](#chapter-1--getting-started)
  - [1.1 What PRISM Does](#11-what-prism-does)
  - [1.2 Prerequisites](#12-prerequisites)
  - [1.3 Installation](#13-installation)
  - [1.4 Files PRISM Needs](#14-files-prism-needs)
  - [1.5 Running PRISM](#15-running-prism)
  - [1.6 Running Tests](#16-running-tests)
- [Chapter 2 — Operating PRISM](#chapter-2--operating-prism)
  - [2.1 The Interface at a Glance](#21-the-interface-at-a-glance)
  - [2.2 Main Menu](#22-main-menu)
  - [2.3 `check` — System Status and Diagnostics](#23-check--system-status-and-diagnostics)
  - [2.4 `tasks` — Manage System Tasks / R Scripts](#24-tasks--manage-system-tasksr-scripts)
  - [2.5 `participants` — Manage Participants](#25-participants--manage-participants)
  - [2.6 `logs` — View Logs](#26-logs--view-logs)
  - [2.7 `settings`](#27-settings)
  - [2.8 `shutdown` and `exit`](#28-shutdown-and-exit)
- [Chapter 3 — Debugging PRISM: an RA's Triage Guide](#chapter-3--debugging-prism-an-ras-triage-guide)
  - [3.1 First Checks](#31-first-checks)
  - [3.2 Running Diagnostics](#32-running-diagnostics)
  - [3.3 Reading Logs and the Transcript](#33-reading-logs-and-the-transcript)
  - [3.4 Common Error Messages and What They Mean](#34-common-error-messages-and-what-they-mean)
  - [3.5 Common Scenarios](#35-common-scenarios)
  - [3.6 When and How to Escalate](#36-when-and-how-to-escalate)
- [Appendix A — Repository Layout and Data Files Reference](#appendix-a--repository-layout-and-data-files-reference)
- [Appendix B — For Maintainers: PRISM's Code Organization](#appendix-b--for-maintainers-prisms-code-organization)

---

# Chapter 1 — Getting Started

## 1.1 What PRISM Does

PRISM runs two things:

- **The server** (`run_prism.py`) — the background process that actually
  does the work: sending scheduled surveys, serving the Qualtrics-facing
  endpoints, and running scheduled background tasks (like R scripts). It
  must be running for anything else to work.
- **The interface** (`prism_interface.py`) — the terminal menu program RAs
  interact with day to day. It talks to the server over HTTP; it never
  touches participant data or the schedule directly. If the server isn't
  running, most menus will tell you PRISM is "not running or inaccessible."

## 1.2 Prerequisites

You'll need three things set up before PRISM will run:

1. **Git** — used to download ("clone") this repository.
   - Windows: install [Git for Windows](https://git-scm.com/download/win),
     which also gives you "Git Bash," a terminal you can use for every
     command in this manual.
   - Linux/macOS: Git is usually already installed. Check with
     `git --version` in a terminal; if that fails, install it via your
     system's package manager (e.g. `sudo apt install git` on Ubuntu,
     `brew install git` on macOS).
2. **Python 3.12 or newer** — the language PRISM is written in.
   - Windows: install from [python.org](https://www.python.org/downloads/).
     **Check the "Add python.exe to PATH" box during install** — this is the
     single most common thing that goes wrong on Windows setup.
   - Linux/macOS: usually already installed. Check with `python3 --version`.
3. **Access to the study's research drive**, mapped over the lab's VPN. This
   holds the real participant data, credentials, and message text — PRISM
   won't run without it. Ask your PI or the lab's IT contact for VPN
   credentials and drive-mount instructions if you don't already have them;
   see [Appendix A](#appendix-a--repository-layout-and-data-files-reference)
   for exactly what PRISM reads from the drive once it's mounted.

Once you have those, open a terminal (Git Bash on Windows; Terminal on
Linux/macOS) and download the repository:

```
git clone https://github.com/jjcurtin/prism.git
cd prism
```

Every command in this manual assumes you're inside the `prism` folder you
just cloned.

## 1.3 Installation

Installation is a one-time step (redo it only if the maintainer tells you
dependencies changed). It creates a private Python environment inside the
repo (`.venv/`) so PRISM's dependencies never conflict with anything else on
your machine, then installs everything PRISM needs into it.

**Windows** — open **PowerShell** in the `prism` folder (Shift+Right-click
inside the folder in File Explorer → "Open PowerShell window here," or `cd`
to it from an existing PowerShell window), then run:

```powershell
.\prism.ps1 setup
```

If you see a red error mentioning "execution of scripts is disabled on this
system," PowerShell is blocking the script for security reasons — this is
normal on a fresh Windows machine. Run this once to allow it for your
current session, then re-run the setup command above:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**Linux / macOS:**

```bash
make setup
```

(If your machine doesn't have `make`, `python3 tasks.py setup` does the
exact same thing.)

Setup does **not** configure PRISM for your specific study environment —
that comes from the research drive (see the next section). Setup only
installs the code's dependencies.

## 1.4 Files PRISM Needs

Beyond the code (installed above), PRISM reads several files and folders at
startup. Most of these need no action from you — they're either already in
the repo, created automatically, or delivered by the research drive once
it's mounted. Only one is yours to create by hand.

- **`environment`** *(repo root, git-ignored)* — a one-line file containing
  `dev` or `prod`. Nothing to do: PRISM creates this automatically the first
  time it runs, defaulting to `dev`. Only relevant if you're intentionally
  switching a checkout to `prod`. See [1.5](#15-running-prism) for how this
  differs from *mode*.
- **`config/repo_paths.csv`** and **`config/uiconfig.txt`** *(tracked,
  already in your checkout)* — resolution facts for this checkout (where
  logs live locally, how the research drive mounts, interface display
  defaults). Nothing to do unless the maintainer specifically tells you this
  checkout's drive mount is nonstandard. Full schema in
  [Appendix A](#appendix-a--repository-layout-and-data-files-reference).
- **`api/`** *(git-ignored — not present in a fresh checkout)* — Qualtrics
  and Twilio credentials plus SMS message text. This comes entirely from the
  research drive once it's mounted; you never create or edit these files
  yourself. If PRISM's transcript says something like "Failed to load
  Qualtrics API keys," that almost always means the drive isn't mounted or
  reachable yet, not that a local file is missing — see
  [3.5](#35-common-scenarios).
- **The rest of `config/`** (`study_coordinators.csv`,
  `system_task_schedule.csv`) **and participant data**
  (`study_participants.csv`, `reminders.csv`) — same story as `api/`:
  drive-sourced, appear automatically once you're connected, not something
  you author by hand. Prefer editing participants/tasks through the RA
  interface's menus over touching these CSVs directly — the interface
  validates formats (phone numbers, times, IDs) before writing, so a typo
  gets caught immediately instead of failing silently later. Full schema in
  [Appendix A](#appendix-a--repository-layout-and-data-files-reference).
- **`scripts/`** *(git-ignored — the one thing you create yourself)* — R
  scripts for the `RUN_R_SCRIPT` task type live here, auto-detected by
  filename; nothing creates this directory automatically, and a
  `RUN_R_SCRIPT` task fails with a clear "does not exist" error until it's
  there. Its exact location comes from the drive's own `paths.csv` (its
  `scripts` key, a *separate* file from `config/repo_paths.csv` above) — a
  relative value there resolves against your local repo checkout (not the
  drive), so it's usually just `scripts/` at the repo root, but ask your PI
  to confirm if unsure. Create that directory (`mkdir scripts`) and drop
  `.R` script files in directly; no further registration step needed.

## 1.5 Running PRISM

PRISM has two separate pieces you'll typically run in two separate
terminals: the **server** and the **interface**. Start the server first.

Two settings look similar but control different things, so it's worth being
clear on which is which:

- **Mode** (`silent`/`live`) — whether the server actually sends real
  texts. Chosen every time you start the server; there's no default you can
  rely on being safe — you type `silent` or `live` explicitly every time.
- **Environment** (`dev`/`prod`, the `environment` file from
  [1.4](#14-files-prism-needs)) — which set of credentials and study data
  the server loads from the research drive. Set once per checkout.

A `dev`-environment checkout run in `live` mode still sends real texts —
just using whatever dev-environment Twilio credentials are configured. The
two aren't the same axis; don't confuse them.

**Windows** — start the server (silent mode — safe, does not send real
texts):

```powershell
.\prism.ps1 run-silent
```

Leave that terminal running, open a **second** PowerShell window in the
same `prism` folder, and launch the RA interface:

```powershell
.\prism.ps1 interface
```

To stop the server, go back to its terminal window and press `Ctrl+C` (or
see [3.5](#35-common-scenarios) if that doesn't work).

**Linux / macOS** — start the server (silent mode):

```bash
make run-silent
```

In a second terminal, launch the interface:

```bash
make interface
```

Stop the server with `Ctrl+C` in its terminal.

**Going live** — once you're actually ready to run the live study (real
participants, real texts), the equivalent commands are `.\prism.ps1
run-live` (Windows) / `make run-live` (Linux/macOS) — but don't do this
without explicit sign-off from whoever runs the study. There is
deliberately no default mode; you must type `silent` or `live` every time so
you can't boot a real send by accident.

A successful server start prints something like this to its terminal:

```
INFO - Initializing PRISM application...
INFO - PRISM started in silent mode.
```

(`silent` becomes `live` if you started it with `-mode live`.)

If a PRISM server is already running from this same checkout, a second
attempt to start one refuses instead of running two copies against the same
data:

```
ERROR - Refusing to start: /path/to/repo/.run_prism.pid names process 48213, which is still running. Stop it first (stop_server.py), or remove the PID file yourself if you're certain it's stale.
```

See [3.5](#35-common-scenarios) if you hit this and aren't sure whether a
real server is actually running.

## 1.6 Running Tests

You generally only need this if you're troubleshooting a problem or a
maintainer asks you to confirm something works. Tests run entirely offline
against fake data — they never touch the research drive or send real texts.

**Windows:**

```powershell
.\prism.ps1 test-all
```

**Linux / macOS:**

```bash
make test-all
```

Both run PRISM's full offline test suite (currently 700+ automated checks).
If everything passes, you'll see a summary ending in something like `...
passed` with no `FAILED` lines. If something fails, copy the full output
and send it to the maintainer rather than trying to interpret it yourself
(see [3.6](#36-when-and-how-to-escalate)).

There are also narrower test commands if you only want one piece —
`test-server` / `test-client` (swap `make` for `.\prism.ps1` on Windows) —
and a separate `test-integration` suite that talks to the real Qualtrics/
Twilio/drive services with real dev credentials; that one is local-only,
isn't run automatically, and cleanly skips itself if dev credentials aren't
configured on your machine. Details in
[Appendix B](#appendix-b--for-maintainers-prisms-code-organization).

`python tasks.py --help` (or `python3 tasks.py --help` on Linux/macOS) lists
every available command directly, with its own `--help` for a given
command's options — this is the canonical, cross-platform reference
underneath both `make` and `.\prism.ps1`, if you ever need a command that
isn't listed in this manual. Running `make` with no target, or
`.\prism.ps1` with no target, prints the same list.

---

# Chapter 2 — Operating PRISM

## 2.1 The Interface at a Glance

Everything an RA does day-to-day — checking on the server, managing
participants, scheduling tasks, reading logs, and adjusting your own
display settings — happens through `prism_interface.py`'s menu tree.

**Two ways to navigate:**

1. **Click through menus** — just type the word (or, in the participant
   table, the sub ID) shown on screen for the option you want. This always
   works and needs no memorization.
2. **Type a command directly** — most actions are also available as a
   command you can type from *any* menu, not just the one it "belongs" to.

**Finding commands** — `command` or `?` lists every available command;
`command <query>` or `?<query>` searches for commands matching `<query>`
(e.g. `?participant` surfaces participant-related commands). If nothing
matches:

```
No commands found matching your query.
```

**Chaining commands** — you can string several commands (and their inputs)
together in one line using `/` before each command and `?` before each
input:

```
/tasks/add/rscript?2?00:00:00
```

This walks into `tasks`, then `add`, then `rscript`, selects script `2`,
and schedules it for `00:00:00` — all in one line, instead of navigating
each screen by hand. Commands and inputs can be in any order; each `?`
input attaches to the command immediately to its left. Executing a chain
prints each step as it runs:

```
Executing command: tasks
Executing command: add
Executing command: rscript
Input values: ['2', '00:00:00']
```

Append `*N` to a chain to repeat the whole thing `N` times, e.g.
`/tasks/execute/rscript?1*3`.

**Jumping back to the main menu** — `ENTER` only backs out one menu level
at a time, so getting back to the main menu from several levels deep
normally takes one `ENTER` per level. Type `home` instead to jump straight
back to the main menu from anywhere, in one step.

**The three prompts** — PRISM shows a different prompt depending on what it
expects from you:

- `prism>` — the normal prompt; runs any command.
- `twilio>` — whatever you type here is sent as an SMS to participant(s).
- `ENTER to Continue>` — just press Enter; no commands work here.

## 2.2 Main Menu

After starting the interface, you land on the Main Menu. Above the list of
commands is a status panel — recent system task activity, today's EMA/
feedback send counts, and when PRISM started — refreshed every time this
screen redraws:

```
===================================================================================================================================================
                                                                       Main Menu
===================================================================================================================================================

------------------------------------------------------------------------------------------------------------------------------------------------------
Recent System Tasks
  09:00:00  CHECK_SYSTEM #482910 - SUCCESS
  23:30:05  RUN_R_SCRIPT #119284 - FAILURE
------------------------------------------------------------------------------------------------------------------------------------------------------
  PRISM started: 2026-07-12 08:00:03
  EMA sent today - on study: 3/10   all participants: 3/12
  Feedback sent today - on study: 1/10   all participants: 1/12
------------------------------------------------------------------------------------------------------------------------------------------------------

------------------------------------------------------------------------------------------------------------------------------------------------------
| command      | Global Command Menu                                                                                                                |
| check        | System Status and Diagnostics                                                                                                      |
| tasks        | Manage System Tasks/R Scripts                                                                                                      |
| participants | Manage Participants                                                                                                                |
| logs         | View Logs                                                                                                                          |
| settings     | Settings                                                                                                                           |
| shutdown     | Shutdown PRISM                                                                                                                     |
| exit         | Exit PRISM User Interface                                                                                                          |
------------------------------------------------------------------------------------------------------------------------------------------------------
```

(Exact column widths depend on your configured window width —
[2.7](#27-settings) — this is illustrative, not pixel-exact.)

**Recent System Tasks** shows up to the last 5 completed system tasks (see
[2.4](#24-tasks--manage-system-tasksr-scripts)), scanned from the transcript
— each task logs a "completed with status: SUCCESS/FAILURE" line when it
finishes, whether run on schedule or via `tasks execute`.

**Send counts** show how many *unique* participants have received today's
EMA/feedback survey so far — a participant sent to more than once today
(e.g. once by the schedule, once by an RA's ad hoc resend) still only
counts once, so the fraction never exceeds its own total. Reminders don't
count toward this — only the primary EMA/feedback send does. Both counts
reset automatically at midnight.

**PRISM started** shows the exact moment the currently-running server
process started (not how long it's been running — for that, see `check`'s
uptime, [2.3](#23-check--system-status-and-diagnostics)).

- `check` — system status and diagnostics ([2.3](#23-check--system-status-and-diagnostics))
- `tasks` — schedule, run, or remove system tasks and R scripts ([2.4](#24-tasks--manage-system-tasksr-scripts))
- `participants` — add, edit, remove, and message study participants ([2.5](#25-participants--manage-participants))
- `logs` — view transcripts, EMA/feedback logs, and the interface log ([2.6](#26-logs--view-logs))
- `settings` — display and system preferences for the interface itself ([2.7](#27-settings))
- `command` — search/list every command available anywhere in PRISM
- `shutdown` — stop the PRISM server (asks for confirmation first)
- `exit` — close this interface only; the PRISM server keeps running
- `readme` — redisplay the startup message (`readme set` toggles whether it
  shows automatically on launch) — not shown on the Main Menu screen itself,
  but always available as a typed command

If something looks wrong, `check` will tell you if PRISM is reachable and
let you run diagnostics, and `logs` lets you see recent activity (including
error messages) without needing anyone to dig into files on the server.
Chapter 3 walks through this in more detail.

## 2.3 `check` — System Status and Diagnostics

Reached from the Main Menu with `check`. Use this when you want to confirm
PRISM is actually running before you report a problem, or after making a
change you want to sanity-check.

Every time you open this menu it shows:

```
Checking PRISM status and system uptime...
------------------------------------------------------------------------------
Mode: silent
As of last check, PRISM has been up for 2:14:07.
------------------------------------------------------------------------------
```

If the server isn't reachable, you'll see:

```
Error: PRISM not running or inaccessible.
```

**Running diagnostics** — type `diagnostics` to have PRISM run its internal
system check (verifying packages, folders, required files, API
connectivity, and participant data).

- Success prints:

  ```
  Success: System checks complete. No issues found.
  ```

- Failure prints the last 25 lines of the transcript so you (or whoever you
  escalate to) can see what went wrong, followed by:

  ```
  Error: Failure detected. Please check the transcript for details.
  ```

  See [2.6](#26-logs--view-logs) if you want to look at more than 25 lines.

## 2.4 `tasks` — Manage System Tasks / R Scripts

Reached from the Main Menu with `tasks`. This is where you schedule
background work for PRISM — built-in system tasks (like the system health
check) as well as R scripts.

Opening this menu always shows the current schedule first:

```
Scheduled Tasks
--------------------------------------------------------------------------------
1: CHECK_SYSTEM @ 06:00:00 - Run Today: True
2: RUN_R_SCRIPT @ 23:30:00 nightly_summary.R - Run Today: True
--------------------------------------------------------------------------------
```

If nothing is scheduled:

```
No tasks scheduled.
```

**Options:**

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

**Tips:**

- The number you use with `remove` refers to that task's position in the
  schedule as printed *right now* — if the schedule changes, re-check it
  before removing by number.
- `execute` runs something immediately without adding it to the schedule;
  use `add` if you want it to happen automatically going forward.

## 2.5 `participants` — Manage Participants

Reached from the Main Menu with `participants`. This is where you add,
review, edit, message, and remove study participants. Participant data
ultimately lives in `config/study_participants.csv`, but you should manage
it through this menu rather than editing that file by hand.

### The participant list

Opening `participants` shows every participant as a table, one row per
participant — like the underlying CSV:

```
Enter a participant's sub ID to select them, or choose another option.
Current Display Mode: unique_id
Current Filter Settings: All
--------------------------------------------------------------------------------
SUBID     INITIALS  UNIQUE_ID  ON_STUDY  PHONE_NUMBER
--------------------------------------------------------------------------------
1001      JMS       100000001  yes       6085551234
1002      AKT       100000002  yes       6085555678
1003      RQP       100000003  no        6085559012
--------------------------------------------------------------------------------
Showing 1-3 of 3 participants.
```

Type a participant's sub ID directly to open their record, from anywhere in
the list, regardless of current sort order or which page is currently on
screen. (If two participants ever share a sub ID — not something PRISM
prevents on load — the second one's entry falls back to being keyed by its
unique ID instead, so neither becomes unreachable.)

If there are more participants than fit on one screen (the page size
matches your configured window height — [2.7](#27-settings), default 20
rows), only `next`/`previous` show up (whichever is actually usable) to
page through the table; sub-ID entry always works for any participant
regardless of which page is showing.

### Other options on this screen

- `add` — add a new participant (see below)
- `schedule` — print every on-study participant's upcoming EMA/feedback
  send times, sorted chronologically:

  ```
  Participant Task Schedule:
  100000001: ema at 09:00:00 - On Study: True
  100000002: feedback at 09:00:00 - On Study: True
  100000001: feedback_reminder at 15:00:00 - On Study: True
  ```

  (Off-study participants' tasks are never shown here, even though they
  still technically exist internally — see [Appendix B](#appendix-b--for-maintainers-prisms-code-organization).)
- `refresh` — reload participants from the CSV file (use this if the file
  was edited outside of PRISM)
- `announcement` — send an SMS to some or all participants. Asks first
  whether to restrict to participants currently on-study:

  ```
  Send to participants on study only? (y/n): [default = y]:
  ```

  then opens the `twilio>` prompt for your message text. The server-side
  transcript records this as an announcement, whether it went to everyone
  or only on-study participants, and logs each attempted send by
  participant unique ID (not phone number).
- `send_ema` / `send_feedback` — send today's EMA or feedback survey to
  every participant right now, in one action (also asks the same
  on-study-only question above). Useful for re-sending after an outage.
- `ema_on` / `ema_off` / `feedback_on` / `feedback_off` — pause or resume a
  survey type's *scheduled* sends study-wide for the rest of the day (e.g.
  during a Qualtrics outage). This does **not** affect `send_ema`/
  `send_feedback` above, or an individual participant's ad hoc `survey`
  send — those are explicit, deliberate actions, not part of the automatic
  schedule this pauses. Each command's menu description shows the survey
  type's current status (`ON` or `PAUSED`). The pause automatically clears
  at midnight — there's nothing to remember to turn back on the next day.
- `remove` — remove a participant by their unique ID
- `sort` — change list ordering: by name, unique ID, or on-study status
- `filter` — show only on-study, only off-study, or all participants

### Adding a participant

`add` walks you through: first name, last name, a 9-digit unique ID (leave
blank and PRISM will generate one for you), on-study yes/no, phone number
(optional), and four daily times in `HH:MM:SS` format — EMA send, EMA
reminder, feedback send, and feedback reminder. If you leave a time blank,
or type it in the wrong format, PRISM fills in a sensible default and tells
you so — you can always fix it later from the participant's record.

### A participant's record

Selecting a participant (by sub ID) shows all of their fields, numbered —
type a number to edit that field. You can also:

- `remove` — remove this participant
- `survey` — send them an ad-hoc EMA or feedback survey right now
- `message` — send them a custom SMS

### Tips

- Unique IDs must be exactly 9 digits. If you type something else, PRISM
  will generate a valid one for you instead.
- `refresh` is a full reload from the CSV — any changes made only through
  this menu are already live, you don't need to `refresh` after using
  `add`, `remove`, or editing a field.

## 2.6 `logs` — View Logs

Reached from the Main Menu with `logs`. Use this to check recent activity —
for example, to confirm a survey reminder actually went out, or to see what
happened right before an error.

**Options:**

- `transcript` — today's full activity transcript from the PRISM server
- `ema` — the EMA survey log (survey opens/completions)
- `feedback` — the feedback survey log
- `interface` — the log of what *this* menu interface has done/reported on
  your machine (every "success"/"error" message you've seen locally), kept
  separately from the server-side logs above

Each view prompts you for how many lines you want to see (defaults to the
last 10 if you just press Enter).

You generally shouldn't need to open the underlying log files directly —
this menu reads both server- and interface-side logs for you. Go straight
to the files (see [Appendix A](#appendix-a--repository-layout-and-data-files-reference))
only if you need to search across more history than the menu's line-count
prompt covers.

## 2.7 `settings`

Reached from the Main Menu with `settings`. These are preferences for how
*this copy* of the interface looks and behaves — they don't affect the
PRISM server or your study data, so feel free to experiment.

**Display settings** (`settings display`):

- `print` — show current display settings
- `width` — resize the interface window (80–200 characters)
- `height` — resize the interface window (5–15 lines; note this also
  controls how many rows the participant table shows per page —
  [2.5](#25-participants--manage-participants))
- `align` — toggle whether menu options are right-aligned
- `color` — toggle color output in the terminal (turn this off if your
  terminal doesn't render color well)

**System settings** (`settings system`):

- `params` — advanced tuning:
  - `print` — show current values
  - `threshold` / `best threshold` — how closely a typed command has to
    match a real command before PRISM suggests it (0.0–1.0)
  - `type speed` — how fast header messages type out on screen
  - `delay` — pause between menu redraws
  - `timeout` — how long the interface waits for the PRISM server to
    respond before giving up
- `readme set` — turn the startup README message on or off

If you're not sure what a value should be, `print` first to see the current
setting — the prompt itself tells you the valid range.

## 2.8 `shutdown` and `exit`

- `shutdown` — stops the PRISM server itself (asks for confirmation first).
  Use this instead of closing the server's terminal window when possible —
  it lets PRISM clean up (unlink its PID file, stop background threads)
  before exiting. If the server's terminal is still open, `Ctrl+C` there
  does the same thing.
- `exit` — closes *this copy* of the interface only. The PRISM server keeps
  running, and any other RA's interface connected to it is unaffected.

---

# Chapter 3 — Debugging PRISM: an RA's Triage Guide

This chapter is written for the moment something has gone wrong — a survey
didn't send, the interface won't connect, or a menu action failed — and
you're trying to figure out what happened before deciding whether to fix it
yourself or escalate. Work through it roughly in order; each step narrows
down where the problem actually is.

## 3.1 First Checks

**Is the server even running?** Open `check` from the Main Menu
([2.3](#23-check--system-status-and-diagnostics)). If you see:

```
Error: PRISM not running or inaccessible.
```

the interface can't reach a server at all. This means either nobody started
the server, or it crashed/exited. Check the server's own terminal window if
you (or whoever manages the server) still have it open — if it's not
running, restart it per [1.5](#15-running-prism).

**Is this the correct environment?** Confirm the `environment` file at the
repo root ([1.4](#14-files-prism-needs)) says what you expect (`dev` or
`prod`) — running diagnostics or checking participant data against the
wrong environment's drive folder will look like data is "missing" when
it's actually just pointed at the wrong place.

**Is this the correct mode?** `check` shows `Mode: silent` or `Mode: live`.
If a survey didn't send and you expected it to, and the server is in
`silent` mode, that's the reason — silent mode never sends real texts, by
design ([1.5](#15-running-prism)).

## 3.2 Running Diagnostics

If the server is reachable but something still seems wrong, run
`diagnostics` from the `check` menu. This verifies packages, required
folders and files, API connectivity (Qualtrics/Twilio), the research-drive
connection, and the participant roster (e.g. duplicate IDs).

- `Success: System checks complete. No issues found.` — the structural
  stuff is fine; the problem is likely something specific to one
  participant, one send, or one task (go to [3.3](#33-reading-logs-and-the-transcript)).
- `Error: Failure detected. Please check the transcript for details.` —
  something structural is broken (missing file, drive not mounted, bad
  credential). The 25 transcript lines printed just above this message are
  your best lead — read them before doing anything else.

## 3.3 Reading Logs and the Transcript

Open `logs` ([2.6](#26-logs--view-logs)) and pull the `transcript` — this
is the single best place to see what PRISM actually did, in order,
including errors. Ask for more lines than the default 10 if the event
you're chasing happened a while ago (the transcript is one file per day,
so anything from a previous day needs the file itself — see
[Appendix A](#appendix-a--repository-layout-and-data-files-reference)).

If you're chasing a specific participant's survey activity rather than a
system error, `ema`/`feedback` logs record survey opens/completions
separately from the general transcript.

If in doubt about whether something you're seeing is a *server*-side
problem or specific to *your* copy of the interface, the `interface` log
(also under `logs`) shows only what your terminal has reported locally —
useful for ruling out "is this just my connection to the server" versus
"did the server actually fail to do something."

## 3.4 Common Error Messages and What They Mean

| Message | What it means | What to do |
|---|---|---|
| `PRISM instance is not running or is not accessible. Please start the PRISM server first.` (printed once, at interface startup) | The interface couldn't reach a server at all when it launched. | Start the server first ([1.5](#15-running-prism)), then relaunch the interface. |
| `Error: PRISM not running or inaccessible.` (from `check`) | Same as above, but discovered mid-session — the server was reachable before and isn't now. | Check whether the server crashed or was stopped; see its terminal/transcript. |
| `PRISM server returned an error (status <code>): <message>` | The server responded, but rejected the specific request (e.g. a validation failure, a not-found record). The `<message>` part, when present, names the actual reason. | Read `<message>` — it usually tells you exactly what to fix (bad value, unknown ID, etc.) without needing to escalate. |
| `PRISM server returned an error (status <code>).` (no message) | Same as above, but the server didn't send back a specific reason. | Check the transcript ([3.3](#33-reading-logs-and-the-transcript)) around the time you made the request for more detail. |
| `Connection error occurred while trying to reach the PRISM server.` | The interface can't reach the server's network address at all (not just a rejected request). | Confirm the server process is actually running and on the expected host/port; see [3.5](#35-common-scenarios). |
| `Request timed out. Please check the PRISM server or increase the timeout value.` | The server didn't respond within the configured timeout. | Could mean the server is overloaded or hung. Try again once; if it recurs, escalate. You can also raise the timeout in `settings system params` if this is a consistently slow connection. |
| `ERROR - Refusing to start: <pid file> names process <PID>, which is still running...` | You tried to start a second server while one is already running from this checkout. | See [3.5](#35-common-scenarios) — do not just delete the PID file without checking first. |
| `Failed to load Qualtrics API keys` / similar credential-load errors in the transcript | The research drive isn't mounted or reachable, or the `.api` file on it is empty/malformed. | Confirm your VPN/drive mount is active, then restart the server. If it persists, escalate — this may be a drive-side problem, not something fixable locally. |

## 3.5 Common Scenarios

**A scheduled survey didn't go out.**
1. Check `Mode` in `check` — if `silent`, this is expected; nothing was
   actually sent by design.
2. Check whether that survey type is paused
   (`participants` → `ema_on`/`feedback_on` shows current status — see
   [2.5](#25-participants--manage-participants)). A pause silently skips
   scheduled sends for the rest of that day, by design, but is easy to
   forget about.
3. Check the participant is on-study — off-study participants' scheduled
   sends are skipped.
4. Check the transcript around the expected send time for a skip or error
   line naming that participant.
5. If none of the above explain it, use `send_ema`/`send_feedback` (or the
   participant's own `survey` option) to send it now, and escalate the
   original miss to the maintainer with the transcript excerpt.

**The server won't start — "Refusing to start" error.**
This means the server's PID file already names a process it believes is
still alive. Before doing anything destructive:
1. Check whether a server is genuinely already running (ask other RAs, or
   check for an existing terminal window running `run_prism.py`).
2. If a real server *is* running, you don't need to start another one —
   just launch the interface against it.
3. If you're confident no real server is running (e.g. the machine was
   restarted and the old process is definitely gone), use `stop_server.py`
   to clean up rather than manually deleting the PID file — it checks
   liveness properly instead of guessing.
4. If `stop_server.py` reports it can't find a PID file and falls back to
   listing candidate processes by name instead of killing them
   automatically, verify each listed process before manually killing
   anything — this fallback deliberately does not auto-kill, since a
   command-line pattern match can catch unrelated processes.

**Credentials or drive-sourced data look missing.**
Almost always means the research drive isn't mounted/reachable at the
moment PRISM tried to read from it, not that something is actually
misconfigured. Reconnect your VPN/drive mount and restart the server. See
[1.4](#14-files-prism-needs) and
[Appendix A](#appendix-a--repository-layout-and-data-files-reference) for
exactly what's expected to live on the drive.

**A participant can't be found / a menu says "not found."**
Double-check the sub ID or unique ID you typed against the participant
table (`participants`, sorted/filtered as needed —
[2.5](#25-participants--manage-participants)). If they're genuinely not in
the list, they may need to be added, or the CSV may need a `refresh` if
someone edited it outside of PRISM.

**Tests fail when running `test-all`.**
This is a maintainer-facing signal — see
[1.6](#16-running-tests) and [3.6](#36-when-and-how-to-escalate). Don't try
to interpret a failing test yourself; copy the full output and send it
along.

## 3.6 When and How to Escalate

Escalate to whoever maintains PRISM's code (not just runs the study) when:

- Diagnostics fail structurally (missing files, drive/API connectivity)
  and reconnecting the drive/VPN doesn't fix it.
- The same error recurs across restarts, or across multiple participants.
- `test-all` reports any `FAILED` lines.
- You're about to do anything that feels destructive and irreversible
  (deleting a PID file, editing a CSV by hand, force-killing a process) and
  aren't fully sure it's safe.

When you escalate, include:

1. What you were trying to do, and what you expected to happen instead.
2. The exact error message(s) — copy-paste, don't paraphrase.
3. Relevant transcript lines from around the time of the problem
   ([3.3](#33-reading-logs-and-the-transcript)).
4. Whether it's reproducible (does it happen again if you retry the same
   action?).
5. Current `Mode`/environment from `check`, so the maintainer isn't
   guessing which credentials/data set was in play.

---

# Appendix A — Repository Layout and Data Files Reference

This appendix covers what used to live in `config/README.md`,
`data/README.md`, `logs/README.md`, and the "Navigating this repo" section
of the old root `README.md`.

## Top-level folders

- **`api/`** *(git-ignored, created at runtime)* — plaintext API credential
  CSVs (Qualtrics, Twilio, the research drive). Not present in a fresh
  checkout; sourced from the research drive.
- **`config/`** — configuration CSVs PRISM needs to run (participant
  roster, task schedule, coordinator list). Schema below.
- **`data/`** — where PRISM would write output pulled down from external
  services while a study is running. Nothing here is tracked by git.
  Currently unused: the data-pulldown tasks that used to write here
  (Qualtrics survey responses, FollowMee location data) were both removed
  entirely — PRISM does not pull down or store any Qualtrics survey
  response data; surveys are still sent to participants, just as a bare
  link. Kept in case a future task needs a repo-root-relative data
  directory again.
  - `messages/` — reserved for message/communication logs. Not currently
    written to by anything in this version of PRISM — SMS is sent live via
    Twilio without keeping a local copy here.
  - The `check` menu's diagnostics touch this folder as part of confirming
    PRISM's overall health. There's currently no automatic cleanup — files
    accumulate here for as long as the study runs, so periodically
    archiving `data/` is worth doing on a long study.
- **`logs/`** — where the running PRISM server writes its activity logs —
  one text file per day, appended to as the day goes on. Nothing here is
  tracked by git; empty until PRISM has actually run.
  - `transcripts/` — the app-wide activity log: SMS sends, task runs, data
    pulldowns, errors — anything logged from the server side,
    `{date}_transcript.txt`.
  - `interface_logs/` — separate from the above: a log of what *your local
    copy* of the terminal interface has reported to you (every
    success/error message you've seen on screen), not the server's own
    logs.
  - You generally shouldn't need to open these files directly — the `logs`
    menu in the interface ([2.6](#26-logs--view-logs)) reads both for you.
    Go straight to the files only if you need to search across more
    history than the menu's line-count prompt covers.
- **`scripts/`** *(git-ignored, create this yourself — see
  [1.4](#14-files-prism-needs))* — R scripts for the script pipeline;
  auto-detected by the task system.
- **`src/`** — the PRISM server, interface, and system tasks. See
  [Appendix B](#appendix-b--for-maintainers-prisms-code-organization).

## Where drive-sourced files actually come from

`run_prism.py`'s `load_paths()`/`load_api_keys()` read
`S:/optimize/prism/<environment>/` (`<environment>` from the git-ignored
`environment` marker file at the repo root, `dev` or `prod`) for everything
study-specific: the `api/` folder (Qualtrics/Twilio/etc. credentials + SMS
message text), and most of `config/` (`study_coordinators.csv`,
`system_task_schedule.csv`). `study_participants.csv`/`reminders.csv` live
under a separate `data_raw/participants/` path on the same drive
(`dev_`-prefixed for the dev environment), per that environment's
`paths.csv`.

On Linux, the drive mounts at `/mnt/research_drive` (WiscVPN + CIFS — see
`research-drive-map`/`wisc-connect` aliases); on Windows the research drive
is **always** mapped to `S:` (a fixed lab convention, not a per-machine
setting) — that's why `repo_paths.csv`'s `drive_mount_windows` value and
the `S:/...` literals baked directly into `run_prism.py` are the same
constant; there's no per-machine Windows drive-letter substitution to
worry about.

`config/` itself holds two files that are **tracked** in this repo (unlike
everything else in that folder, which is drive-sourced or git-ignored):

- `repo_paths.csv` — internal resolution facts for this repo checkout
  itself (where logs live locally, how the drive mounts per-platform,
  which drive subpath this project is under) — as opposed to study-specific
  data, which comes from the drive.
- `uiconfig.txt` — interface defaults (display tunables). This is generic,
  not study-specific or secret, so unlike the drive-sourced files it ships
  with the repo rather than requiring a fresh clone to copy it from the
  drive first.

## Data file schemas (from the real files on the drive)

`study_participants.csv`:
```
initials,subid,unique_id,on_study,phone_number,ema_time,ema_reminder_time,feedback_time,feedback_reminder_time
```

`reminders.csv`:
```
subid,unique_id,on_study,remind_ema,remind_feedback
```
`remind_ema`/`remind_feedback` are `"yes"`/`"no"` flags meaning "should
this participant still be reminded about today's EMA/feedback survey" —
`"no"` means they've already opened it, so a scheduled reminder send is
skipped. Nothing in PRISM's own codebase writes this file; it's populated
by an external process.

`study_coordinators.csv`: `name,phone_number` (10 digits) — who gets texted
if a background task or system check fails (in live mode).

`system_task_schedule.csv`: `task_type,task_time,r_script_path,run_today` —
`task_type` must match a task class in `src/system_tasks/` (see
[Appendix B](#appendix-b--for-maintainers-prisms-code-organization)).

R scripts for the `RUN_R_SCRIPT` task are auto-detected from wherever
`r_scripts_dir` points — drop scripts there directly.

## A note on editing these by hand

You *can* edit these CSVs directly, but it's safer to make changes through
the `prism_interface.py` menus where possible (`participants`, `tasks` —
[2.4](#24-tasks--manage-system-tasksr-scripts),
[2.5](#25-participants--manage-participants)) — the interface validates
formats (phone numbers, times, IDs) before writing, whereas a hand-edited
CSV with a typo (wrong time format, missing column) can fail silently at
runtime. If you do edit a file directly while PRISM is running, use
`participants refresh` afterward to reload it.

---

# Appendix B — For Maintainers: PRISM's Code Organization

This appendix covers what used to live in `src/README.md` and its
subfolder READMEs (`system_tasks/`, `task_managers/`,
`user_interface_menus/` and its submenus), plus `tests_integration/
README.md`. It's aimed at whoever maintains PRISM's code rather than
day-to-day RA use, but is useful background for understanding *why* the
interface behaves the way Chapters 2–3 describe.

## `src/` — the two things you actually run

- **`run_prism.py`** — starts the PRISM server (`python run_prism.py -mode
  {silent,live}`). This is the process that does the real work: sending
  surveys, serving the Qualtrics-facing endpoints, running scheduled tasks.
  Must be launched from inside the `src/` folder. In `live` mode it will
  also text study coordinators if a background task fails.
- **`prism_interface.py`** — the terminal menu program RAs actually
  interact with day to day. It talks to the running server over HTTP; it
  never touches participant data or the schedule directly.

## `src/` — everything else

- **`_routes.py`** — the server's API surface (every URL the interface
  calls).
- **`_helper.py`** — small shared utilities (sending SMS via Twilio,
  clearing the terminal).
- **`system_tasks/`** — the individual background jobs PRISM can run or
  schedule (system health checks, R scripts, etc.) — details below.
- **`task_managers/`** — the scheduling engine that decides when those
  jobs (and participant SMS sends) actually fire — details below.
- **`user_interface_menus/`** — the code behind every screen in
  `prism_interface.py` — details below.

## `src/system_tasks/` — background jobs

Each task type shows up by name in the `tasks add system` / `tasks
execute` menus.

- **`CHECK_SYSTEM`** — the "run diagnostics" task behind the `check` menu.
  Verifies the folder layout, the research-drive connection, and the
  participant roster (duplicate IDs).
- **`RUN_R_SCRIPT`** — runs a single R script. Any script placed in the
  repo's `scripts/` folder is automatically picked up and offered as a
  choice in the `tasks add rscript` menu — you don't need to register it
  anywhere.

If a scheduled task fails, whoever is on `config/study_coordinators.csv`
gets a text about it (in live mode).

**Adding a new task type:** task types are **statically registered**, not
auto-discovered — there's no filesystem-listing/dynamic-import mechanism,
so adding one means updating a registry by hand:

- Create a new file directly in `src/system_tasks/`: lowercase,
  underscore-separated, with a leading underscore (`_my_new_task.py`).
- Inside it, define a class matching the filename in `TitleCase` (e.g.
  `_check_system.py` → `CheckSystem`) that subclasses `SystemTask` and
  implements `run()`, returning `0` on success and non-zero on failure.
  `run()` must also set `self.task_type` (e.g. `self.task_type =
  "CHECK_SYSTEM"`) — that string is what `config/system_task_schedule.csv`
  and the `tasks` menu use to refer to it.
- Import the class and add a `task_type: ClassName` line to the
  `TASK_CLASSES` dict in `task_managers/_system_task_manager.py` — that
  dict is the single source of truth for which task types exist. A new
  task file has no effect until it's registered there, and becomes
  available on the next PRISM restart (no hot-reload).

## `src/task_managers/` — the scheduling engine

This is what actually decides "it's 4pm, time to text this participant
their EMA survey" or "it's midnight, time to run a scheduled task." RAs
don't interact with this folder directly; it's what powers the `tasks` and
`participants` menus.

- There are two task managers, each running on its own background thread
  so they don't block each other or the server:
  - **`SystemTaskManager`** — runs the jobs in `system_tasks/` on the
    schedule in `config/system_task_schedule.csv`.
  - **`ParticipantManager`** — owns the participant roster
    (`config/study_participants.csv`) and schedules each participant's
    daily EMA/feedback/reminder texts based on their individual times.
- Both check once a second for anything due, and use a first-in-first-out
  queue — so if several things are due at once, they run in the order they
  were queued rather than all at once.
- Both share the same underlying base class (add/remove a task, check
  what's due), and each adds its own specific behavior on top (e.g. the
  participant manager also knows how to send SMS; the system task manager
  knows how to dynamically load a task class by name).
- An off-study participant's recurring tasks are *not* removed from the
  manager's internal task list when they go off-study — they're skipped at
  send time instead. This is why the `participants schedule` command
  ([2.5](#25-participants--manage-participants)) explicitly filters to
  on-study participants before printing: showing an off-study participant's
  task there would be misleading (it looks scheduled, but will never
  actually fire).

If a survey text didn't go out, or a scheduled task didn't run, this layer
is responsible — the `logs` menu's transcript view is the best way to see
what these managers actually did (or failed to do) around the time in
question.

## `src/user_interface_menus/` — the interface's code

Mirrors the menu tree an RA sees: `check/`, `tasks/`, `participants/`,
`logs/`, `settings/`, plus a shared `utils/` package for navigation,
display, and command-chaining machinery (the mechanics behind [2.1](#21-the-interface-at-a-glance)).

Known rough edges, for anyone picking up maintenance work here:

- Field-level edit validation on an existing participant's record is
  inconsistent — `on_study` and the four survey-time fields are validated
  on edit, but `first_name`, `last_name`, `unique_id`, and `phone_number`
  are not, even though `unique_id` and `phone_number` *are* validated at
  add-time. Editing a participant's `unique_id` to something invalid after
  creation currently isn't caught.
- The unique-ID collision-avoidance loop in `add_participant_menu`
  generates a replacement ID on a collision but doesn't re-check that
  replacement against the existing list, so a second (rare) collision
  would go undetected.
- A failed field update (`PUT .../update_participant/...`) only shows a
  generic "Failed to update participant." — the server-side reason, if
  any, isn't surfaced distinctly from that generic message.

## `tests_integration/` — real end-to-end tests

Real end-to-end tests that hit real external services (Qualtrics, the
research drive) using real **dev-environment** credentials, loaded exactly
the way the app itself loads them: via the git-ignored `environment`
marker file at the repo root and the drive-sourced `config_base/api/*.api`
files. Nothing here is mocked.

This is deliberately separate from `tests/` and `tests_interface/` (both
fully offline, no network/drive dependency, gated by CI):

- **Not run in CI.** `.github/workflows/tests.yml` has no secrets
  configured and never will for this directory — these tests depend on the
  research drive being mounted and real dev API tokens being filled in,
  neither of which exists in a GitHub Actions runner.
- **Not in `pytest.ini`'s `testpaths`.** A bare `pytest` from the repo root
  will not pick this directory up.
- **Local-only, run manually:**

  ```
  make test-integration
  ```

  (equivalent to `.venv/bin/python -m pytest tests_integration -v`, run
  from the repo root).

**Credentials:** each test loads a real `PRISM` instance against the real
`environment` marker + drive-sourced `config_base`, then checks whether the
credentials it needs are actually filled in (not still a
`"REPLACE_WITH_..."` placeholder value, which is what the checked-in `.api`
templates on the drive ship with before someone fills in the real dev
values). If they aren't, the test skips with the specific missing/
placeholder field names, rather than failing — this directory is meant to
be safe to run (and skip cleanly) on any machine, whether or not that
machine has the research drive mounted and dev credentials populated.

**What's covered:** `test_environment_files.py` checks, for **both**
`"dev"` and `"prod"` environments, that every file `load_paths()`/
`load_api_keys()` expect actually exists, and that the drive-sourced
`.api`/CSV files are populated beyond their checked-in templates. It skips
per-environment only when that environment isn't set up on this machine at
all (drive not mounted, or `config_base` doesn't exist under it).
