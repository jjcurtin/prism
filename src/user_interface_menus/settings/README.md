# Settings

Reached from the Main Menu with `settings`. These are preferences for how
*this copy* of the interface looks and behaves — they don't affect the
PRISM server or your study data, so feel free to experiment.

## Display settings (`settings display`)

- `print` — show current display settings
- `width` / `height` — resize the interface window (width 80–200, height
  5–15 lines)
- `align` — toggle whether menu options are right-aligned
- `color` — toggle color output in the terminal (turn this off if your
  terminal doesn't render color well)

## System settings (`settings system`)

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
setting, and the prompt itself tells you the valid range.
