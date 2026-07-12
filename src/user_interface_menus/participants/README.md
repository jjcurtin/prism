# Manage Participants

Reached from the Main Menu with `participants`. This is where you add,
review, edit, message, and remove study participants. Participant data
ultimately lives in `config/study_participants.csv`, but you should manage
it through this menu rather than editing that file by hand.

## The participant list

Opening `participants` shows every participant, each entry keyed by their
sub ID (`sub_id (initials, unique_id)`) — type a participant's sub ID directly
to open their record, from anywhere in the list, regardless of current sort
order. (If two participants ever share a sub ID — not something PRISM
prevents on load — the second one's entry falls back to being keyed by its
unique ID instead, so neither becomes unreachable.) Other options on this
screen:

- `add` — add a new participant (see below)
- `schedule` — print every participant's upcoming EMA/feedback send times
- `refresh` — reload participants from the CSV file (use this if the file
  was edited outside of PRISM)
- `announcement` — send an SMS to some or all participants (asks whether to
  restrict to participants currently on-study)
- `send_ema` / `send_feedback` — send today's EMA or feedback survey to
  every participant right now, in one action (also asks whether to
  restrict to participants currently on-study)
- `ema_on` / `ema_off` / `feedback_on` / `feedback_off` — pause or resume a
  survey type's scheduled sends study-wide for the rest of the day (e.g. a
  Qualtrics outage). Doesn't affect `send_ema`/`send_feedback` above, or an
  individual participant's ad hoc `survey` send — those are explicit,
  deliberate actions, not part of the automatic schedule this pauses. Each
  command's description shows the survey type's current status.
- `remove` — remove a participant by their unique ID
- `sort` — change list ordering: by name, unique ID, or on-study status
- `filter` — show only on-study, only off-study, or all participants

## Adding a participant

`add` walks you through: first name, last name, a 9-digit unique ID (leave
blank and PRISM will generate one for you), on-study yes/no, phone number
(optional), and four daily times in `HH:MM:SS` format — EMA send, EMA
reminder, feedback send, and feedback reminder. If you leave a time blank or
enter it wrong, PRISM fills in a sensible default and tells you so — you can
always fix it later from the participant's record.

## A participant's record

Selecting a participant shows all of their fields, numbered — type a number
to edit that field. You can also:

- `remove` — remove this participant
- `survey` — send them an ad-hoc EMA or feedback survey right now
- `message` — send them a custom SMS

## Tips

- Unique IDs must be exactly 9 digits. If you type something else, PRISM
  will generate a valid one for you instead.
- `refresh` is a full reload from the CSV — any changes made only through
  this menu are already live, you don't need to `refresh` after using `add`,
  `remove`, or editing a field.
