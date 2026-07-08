# Src

All of PRISM's Python code lives here: the server, the terminal interface
RAs use, and the background task machinery that runs behind them.

## The two things you actually run

- **`run_prism.py`** — starts the PRISM server (`python run_prism.py -mode
  {test,prod}`). This is the process that does the real work: sending
  surveys, serving the Qualtrics-facing endpoints, running scheduled tasks.
  Must be launched from inside this `src/` folder. In `prod` mode it also
  opens an ngrok tunnel so Qualtrics can reach it, and will text study
  coordinators if a background task fails.
- **`prism_interface.py`** — the terminal menu program RAs actually
  interact with day to day. It talks to the running server over HTTP; it
  never touches participant data or the schedule directly. If the server
  isn't running, most menus will tell you PRISM is "not running or
  inaccessible." See `user_interface_menus/README.md` for the full menu
  guide.

## Everything else in this folder

- **`_routes.py`** — the server's API surface (every URL the interface,
  Qualtrics, and the JS in `../qualtrics_js/` call).
- **`_helper.py`** — small shared utilities (sending SMS via Twilio,
  clearing the terminal).
- **`system_tasks/`** — the individual background jobs PRISM can run or
  schedule (data pulldown, health checks, R scripts, etc.). See
  `system_tasks/README.md`.
- **`task_managers/`** — the scheduling engine that decides when those jobs
  (and participant SMS sends) actually fire. See `task_managers/README.md`.
- **`user_interface_menus/`** — the code behind every screen in
  `prism_interface.py`. See `user_interface_menus/README.md`.
