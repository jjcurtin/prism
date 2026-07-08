# Manage Participants

Reached from the Main Menu with `participants`. This is where you add,
review, edit, message, and remove study participants. Participant data
ultimately lives in `config/study_participants.csv`, but you should manage
it through this menu rather than editing that file by hand.

## The participant list

Opening `participants` shows every participant as a numbered entry
(`Last, First (unique_id)`) — type the number to open that participant's
record. Other options on this screen:

- `add` — add a new participant (see below)
- `schedule` — print every participant's upcoming EMA/feedback send times
- `refresh` — reload participants from the CSV file (use this if the file
  was edited outside of PRISM)
- `announcement` — send an SMS to some or all participants (asks whether to
  restrict to participants currently on-study)
- `remove` — remove a participant by their unique ID
- `access` — jump straight to a participant's record by unique ID (handy if
  you don't want to scroll the list)
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
