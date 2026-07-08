# PRISM Interface Menus

This is the terminal menu system you interact with when you run
`prism_interface.py`. Everything an RA does day-to-day — checking on the
server, managing participants, scheduling tasks, reading logs, adjusting
your own display settings, or asking the built-in Assistant a question —
happens through this menu tree.

## Main Menu

After starting the interface, you land on the Main Menu with these options:

- `help` — documentation, including a dedicated Research Assistant section
  (see `help/README.md`)
- `assistant` — the PRISM Assistant, a natural-language helper (see
  `assistant/README.md`)
- `check` — system status and diagnostics (see `check/README.md`)
- `tasks` — schedule, run, or remove system tasks and R scripts (see
  `tasks/README.md`)
- `participants` — add, edit, remove, and message study participants (see
  `participants/README.md`)
- `logs` — view transcripts, EMA/feedback logs, and the interface log (see
  `logs/README.md`)
- `settings` — display and system preferences for the interface itself (see
  `settings/README.md`)
- `command` — search/list every command available anywhere in PRISM
- `shutdown` — stop the PRISM server (asks for confirmation first)
- `exit` — close this interface only; the PRISM server keeps running

## Getting around

Every screen shows you the options you can type. You don't need to
memorize anything — just read the menu and type the word (or, in
participant/task lists, the number) next to the option you want.

If you want to move faster, most actions also work as typed commands from
anywhere in the app (not just the menu they "belong" to), and can be
chained together or saved as shortcuts. That system is documented in
`utils/README.md`, and in-app under `help ra navigation`.

## If something looks wrong

- `check` will tell you if PRISM is reachable and let you run diagnostics.
- `logs` lets you see recent activity (including error messages) without
  needing anyone to dig into files on the server.
- `help ra` has a written walkthrough of all of the above, and the
  `assistant` menu can answer plain-English questions about how to do
  something.
