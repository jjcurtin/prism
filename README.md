# PRISM

PRISM is a Flask-based backend that runs a behavioral-health research study: it
schedules and sends daily surveys to participants over SMS (delivered as a
bare Qualtrics survey link, with no PRISM-side page personalization) and
gives research staff a terminal UI (`src/prism_interface.py`) to manage
participants and background tasks.

This README is written for research assistants (RAs) setting this up for the
first time, on either a Windows or a Linux/macOS machine — you don't need to
already know Python or the command line to follow it, just be comfortable
copy-pasting commands into a terminal. If something doesn't match what you
see on your screen, ask the lab's PRISM maintainer before improvising.

## Before you start

You'll need three things set up before PRISM will run:

1. **Git** — used to download ("clone") this repository.
   - Windows: install [Git for Windows](https://git-scm.com/download/win),
     which also gives you "Git Bash," a terminal you can use for every
     command below.
   - Linux/macOS: Git is usually already installed. Check with `git --version`
     in a terminal; if that fails, install it via your system's package
     manager (e.g. `sudo apt install git` on Ubuntu, `brew install git` on
     macOS).
2. **Python 3.12 or newer** — the language PRISM is written in.
   - Windows: install from [python.org](https://www.python.org/downloads/).
     **Check the "Add python.exe to PATH" box during install** — this is the
     single most common thing that goes wrong on Windows setup.
   - Linux/macOS: usually already installed. Check with `python3 --version`.
3. **Access to the study's research drive**, mapped over the lab's VPN. This
   holds the real participant data, credentials, and message text — PRISM
   won't run without it. Ask your PI or the lab's IT contact for VPN
   credentials and drive-mount instructions if you don't already have them;
   see `config/README.md` for exactly what PRISM reads from the drive once
   it's mounted.

Once you have those, open a terminal (Git Bash on Windows; Terminal on
Linux/macOS) and download the repository:

```
git clone https://github.com/jjcurtin/prism.git
cd prism
```

Every command below assumes you're inside the `prism` folder you just
cloned.

## Installation

Installation is a one-time step (redo it only if the maintainer tells you
dependencies changed). It creates a private Python environment inside the
repo (`.venv/`) so PRISM's dependencies never conflict with anything else on
your machine, then installs everything PRISM needs into it.

### Windows

Open **PowerShell** in the `prism` folder (Shift+Right-click inside the
folder in File Explorer → "Open PowerShell window here," or `cd` to it from
an existing PowerShell window), then run:

```powershell
.\prism.ps1 setup
```

**If you see a red error mentioning "execution of scripts is disabled on
this system"**, PowerShell is blocking the script for security reasons —
this is normal on a fresh Windows machine. Run this once to allow it for
your current session, then re-run the setup command above:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Linux / macOS

```bash
make setup
```

(If your machine doesn't have `make`, `python3 tasks.py setup` does the
exact same thing.)

### After setup finishes

Setup does **not** configure PRISM for your specific study environment —
that comes from the research drive. Setup only installs the code's
dependencies. The first time you run PRISM (below), it will look for a
git-ignored `environment` file at the repo root containing either `dev` or
`prod`; if that file is missing, PRISM creates one defaulting to `dev` and
expects the research drive to already be mounted with dev credentials in
place. **Never run PRISM in `prod` mode unless you mean to send real texts
to real participants** — see `config/README.md`.

## Running PRISM

PRISM has two separate pieces you'll typically run in two separate
terminals: the **server** (the background process that actually sends
scheduled surveys) and the **interface** (the terminal menu you use to
manage participants and tasks day-to-day). Start the server first.

### Windows

Start the server (test mode — safe, does not send real texts):

```powershell
.\prism.ps1 run-test
```

Leave that terminal running, open a **second** PowerShell window in the same
`prism` folder, and launch the RA interface:

```powershell
.\prism.ps1 interface
```

To stop the server, go back to its terminal window and press `Ctrl+C`.

### Linux / macOS

Start the server (test mode):

```bash
make run-test
```

In a second terminal, launch the interface:

```bash
make interface
```

Stop the server with `Ctrl+C` in its terminal.

### Going to production

Once you're actually ready to run the live study (real participants, real
texts), the equivalent commands are `.\prism.ps1 run-prod` (Windows) /
`make run-prod` (Linux/macOS) — but don't do this without explicit sign-off
from whoever runs the study. There is deliberately no default mode; you must
type `test` or `prod` every time so you can't boot production by accident.

## Running tests

You generally only need this if you're troubleshooting a problem or a
maintainer asks you to confirm something works. Tests run entirely offline
against fake data — they never touch the research drive or send real texts.

### Windows

```powershell
.\prism.ps1 test-all
```

### Linux / macOS

```bash
make test-all
```

Both run PRISM's full offline test suite (currently 650+ automated checks).
If everything passes, you'll see a summary ending in something like
`... passed` with no `FAILED` lines. If something fails, copy the full
output and send it to the maintainer rather than trying to interpret it
yourself.

There are also narrower test commands if you only want one piece —
`test-server` / `test-client` (swap `make` for `.\prism.ps1` on Windows) —
and a separate `test-integration` suite that talks to the real Qualtrics/
Twilio/drive services with real dev credentials; that one is local-only,
isn't run automatically, and cleanly skips itself if dev credentials aren't
configured on your machine.

## Other useful commands

`python tasks.py --help` (or `python3 tasks.py --help` on Linux/macOS) lists
every available command directly, with its own `--help` for a given
command's options — this is the canonical, cross-platform reference
underneath both `make` and `.\prism.ps1`, if you ever need a command that
isn't listed above. Running `make` with no target, or `.\prism.ps1` with no
target, prints the same list.

## Navigating this repo

- **api/** *(git-ignored, created at runtime)* — plaintext API credential CSVs
  (Qualtrics, Twilio, the research drive). Not present in a
  fresh checkout; sourced from the research drive, see `config/README.md`
  for what's required.
- **config/** — configuration CSVs PRISM needs to run (participant roster,
  task schedule, coordinator list). See `config/README.md`.
- **data/** — currently unused (the data-pulldown tasks that used to write
  here were removed; PRISM does not pull down or store any Qualtrics survey
  data). See `data/README.md`.
- **logs/** — transcripts and activity logs. See `logs/README.md`.
- **scripts/** *(git-ignored, created at runtime)* — R scripts for the script
  pipeline; auto-detected by the task system.
- **src/** — the PRISM server, interface, and system tasks. See
  `src/README.md`, which links onward to each subfolder's own README
  (`system_tasks/`, `task_managers/`, `user_interface_menus/` and its 6
  submenus).
