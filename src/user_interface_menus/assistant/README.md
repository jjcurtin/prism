# PRISM Assistant

A natural-language helper you can ask questions in plain English instead of
looking up the exact command yourself.

## How to reach it

- From the Main Menu, type `assistant`.
- From *anywhere* in PRISM, prefix your question with `@` or `assistant `,
  e.g. `@how do I add a participant` or `assistant how do I reschedule a survey`.

## Using it

Once you're at the `assistant>` prompt, just type your question and press
Enter. The Assistant knows the full list of PRISM commands and can suggest
the right one, or explain what a feature does. Press Enter with nothing
typed to leave the assistant menu.

## Things to know

- The first time you use it in a session, it needs Azure credentials
  (`api/azure.api`). If that file doesn't exist yet, PRISM will prompt you
  to enter the key — ask your PRISM administrator if you don't have one.
- The Assistant calls an external AI service, so a slow or unreachable
  internet connection can cause "No response from the assistant" — that's
  not a sign PRISM itself is broken. Try again, and use `check` if you're
  unsure whether the PRISM server is up.
- The Assistant is a convenience layer for finding/understanding commands —
  it doesn't replace the documentation in `help ra`, which is worth reading
  once up front.
