# Navigation & Commands

This is the machinery behind every menu in PRISM — you won't open a menu
called "utils," but everything here is what makes typed commands and command
chaining work throughout the app. This README explains that shared behavior
once instead of repeating it in every other menu.

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

## Jumping back to the main menu

`ENTER` only backs out one menu level at a time, so getting back to the main
menu from several levels deep normally takes one `ENTER` per level. Type
`home` instead to jump straight back to the main menu from anywhere, in one
step.

## The three prompts

PRISM shows a different prompt depending on what it expects from you:

- `prism>` — the normal prompt; runs any command
- `twilio>` — whatever you type here is sent as an SMS to participant(s)
- `ENTER to Continue>` — just press Enter; no commands work here
