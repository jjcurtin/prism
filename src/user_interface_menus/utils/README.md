# Navigation & Commands

This is the machinery behind every menu in PRISM — you won't open a menu
called "utils," but everything here is what makes typed commands, command
chaining, and saved shortcuts work throughout the app. This README explains
that shared behavior once instead of repeating it in every other menu.

## Two ways to navigate

1. **Click through menus** — just type the word (or number) shown on
   screen for the option you want. This always works and needs no
   memorization.
2. **Type a command directly** — most actions are also available as a
   command you can type from *any* menu, not just the one it "belongs" to.

## Finding commands

- `command` or `?` lists every available command.
- `command <query>` or `?<query>` searches for commands matching `<query>`.
  For example, `?participant` will surface participant-related commands.

## Chaining commands

You can string several commands (and their inputs) together in one line
using `/` before each command and `?` before each input:

```
/tasks/add/rscript?2?00:00:00
```

This walks into `tasks`, then `add`, then `rscript`, selects script `2`, and
schedules it for `00:00:00` — all in one line, instead of navigating each
screen by hand. Commands and inputs can be in any order; each `?` input
attaches to the command immediately to its left.

## Saving shortcuts (macros)

If you find yourself typing the same chain repeatedly, save it:

- `$my_shortcut = /participants/sort?name` — save a chain under the name
  `my_shortcut`
- `my_shortcut` — run it later just by typing its name
- `-my_shortcut` — delete a saved shortcut
- `!my_shortcut` — search your saved shortcuts by name

A few shortcuts already come built in — for example, typing `sort_name`,
`sort_id`, or `sort_on_study` re-sorts the participant list without having
to go into `participants/sort` yourself. There's also a `test_all` chain
that walks through participants, tasks, and settings menus back-to-back —
useful as a quick tour of the app or as a smoke test after a PRISM update.

## The three prompts

PRISM shows a different prompt depending on what it expects from you:

- `prism>` — the normal prompt; runs any command
- `twilio>` — whatever you type here is sent as an SMS to participant(s)
- `ENTER to Continue>` — just press Enter; no commands work here
