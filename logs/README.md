# Logs

Where the running PRISM server writes its activity logs — one text file per
day, appended to as the day goes on. Nothing here is tracked by git; this
folder is empty until PRISM has actually run. To read these logs without
opening files directly, use the `logs` menu in the interface (see
`src/user_interface_menus/logs/README.md`), which fetches them from the
server for you.

## Subfolders

- **`transcripts/`** — the app-wide activity log: SMS sends, task runs, data
  pulldowns, errors — anything logged from the server side, `{date}_transcript.txt`.
- **`interface_logs/`** — separate from the above: a log of what *your local
  copy* of the terminal interface has reported to you (every success/error
  message you've seen on screen), not the server's own logs.

## When to look here

You generally shouldn't need to open these files directly — the `logs` menu
in the interface reads both for you and lets you pick how many recent lines
to view. Go straight to the files only if you need to search across more
history than the menu's line-count prompt covers.
