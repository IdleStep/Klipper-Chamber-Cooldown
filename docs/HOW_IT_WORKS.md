# How a cooldown runs

The cooldown is a loop that ticks every 5 s (`loop_seconds`). Each tick does one of three things:
it stops the cooldown, moves to the next phase, or advances the current one.

## Phases

| Phase | What happens | Ends when |
|---|---|---|
| 1 HOLD | The chamber heater keeps its print target. | The hold time passes. Skipped when the profile has no hold. The cooldown goes straight to phase 3 when there is no chamber heater, or when the chamber target at the start is already below the ramp target. |
| 2 RAMP | The target drops `cooldown_ramp_step_c` every `cooldown_ramp_step_seconds`, never below the ramp target. | The target reaches the ramp target. Skipped when the profile has none. |
| 3 REST | The chamber and bed heaters turn off. The exhaust, external_pc and bed fans also turn off when the rest is longer than 0. | The rest time passes. Skipped when the profile has no rest. |
| 4 EXHAUST | The exhaust, external_pc and bed fans are set to the profile speed (0 when `exhaust_enable` is `False`). A speed above 0 that is below a fan's `min_power` (or `off_below`) is raised to that minimum for that fan. | The next tick. |
| 5 CHILL | The cooldown waits. The fans keep running. | The chamber and bed are at or below `chamber_cooled_temp`. |

Every phase prints a numbered banner, so a cooldown always counts from 1/5 to 5/5. A phase the
profile does not use says `skipped`.

While a cooldown runs it prints a progress line every 2 min in the hold, ramp, rest and chill
phases (`report_minutes`) and a temperature line about every 25 s (`status_seconds`):

```
📃 Chamber → 041.0/042.0  •  Bed → 034.0/035.0  •  Cycle 005
```

The arrow compares each reading with the target it shows: `↑` above it, `→` within 2°C below it
(`arrow_band`), `↓` further below. It is not a trend. The shown target is never lower than
`chamber_cooled_temp`.

## Completion and stops

At any phase, the cooldown **completes** once the chamber and the bed are at or below
`chamber_cooled_temp`. It turns off the chamber and bed heaters and the exhaust, external_pc, bed
and part fans, even if you set one of them yourself.

The cooldown **stops** without touching heaters or fans when you change the chamber target, the bed
target, the exhaust fan speed or the bed fan speed by hand, or when a print starts. Turning the
chamber heater off to end a hold early counts as a change: the whole cooldown is cancelled instead
of skipping ahead. A print starts when Klipper's `print_stats.state` becomes `printing`; homing,
probing and other moves do not stop the cooldown.

It **stops and turns the chamber and bed heaters off** when a value in `_COOLDOWN_VARS` is not
valid or when the chamber or bed temperature cannot be read, because it can no longer judge the
temperatures.

## Several devices in one role

These roles of `_HARDWARE_VARS` take several devices, as a name, a comma-separated string or a
list (Hardware Controls 3.4.0 or later): `chamber_heater`, `exhaust_fan`, `external_pc` and
`bed_fans`. The commands act on all of them. These take one device, a single name:
`chamber_sensor` and `bed_heater`.

- **Chamber heaters.** The cooldown reads the first heater that exists for the chamber
  temperature and target, so list the heater that measures the chamber first. A change by hand to
  the target of another heater is not noticed.
- **Fans.** A change to the speed of any one fan of a role stops the cooldown. A speed below a
  fan minimum is raised to the highest `min_power` (or `off_below`) among the fans of the role,
  because all of them get the same speed.

## Idle timeout

When `[idle_timeout]` expires, Klipper runs its idle gcode, which normally turns the heaters off.
A long hold or ramp could outlast it, so `START_COOLDOWN` raises the timeout to cover hold, ramp
and rest plus 10 min (`idle_margin_seconds`), only when that is longer than the timeout in force.
It restores the previous value when the heater is released in phase 3, on completion and on reset.
The exhaust and chill phases are limited by the normal timeout.

The previous value is the one you set with `SET_IDLE_TIMEOUT`, which `idle_timeout_tracking.cfg`
remembers (a pause, a resume or `DISABLE_TIMEOUT` that sets one is covered too). Otherwise it is the
configured one. A shorter timeout set while the longer one is in force applies when the heater is
released.

Klipper counts the idle timeout from the last move, heater command or fan command, not from the
start of the cooldown. A heater or fan command restarts the clock; writing a macro variable or
`M400` does not. Every phase change and every ramp step sends one of those commands, so the timeout
only has to cover the longest stretch between them. `START_COOLDOWN` still checks the whole
cooldown, so it raises the timeout sooner than strictly needed.

`idle_timeout_tracking.cfg` wraps `SET_IDLE_TIMEOUT` with `rename_existing`, and only one config
can do that. If another file of yours already renames it, remove the
`[include idle_timeout_tracking.cfg]` line from `cooldown.cfg`. The cooldown then restores the
configured value. See [design decisions](DESIGN.md) for the limits.

## Profile checks

`START_COOLDOWN` refuses a profile before it starts anything when:

- a value except `exhaust_enable` is missing or not a number (a value in quotes is text),
- a time is negative or the ramp target is negative,
- a ramp target is set and the step is under 0.1°C or the step time is under 5 s,
- the exhaust speed is outside 0.0 to 1.0,
- `exhaust_enable` is not `True` or `False`, or
- the profile name contains a quote mark, semicolon, hash sign or asterisk.

Minutes may be fractional: a 0.5 minute hold is 30 s. `START_COOLDOWN` also refuses settings the
loop cannot run on, such as a `loop_seconds` below 1. The messages are listed in
[Troubleshooting](TROUBLESHOOTING.md).

The loop ticks every 5 s, so a ramp step time is rounded to the nearest 5 s (5 s is the minimum).
`START_COOLDOWN` says so, and the banner and the idle timeout estimate use the rounded time.

## Settings

`_COOLDOWN_SETTINGS` in [`engine.cfg`](../engine.cfg) holds `chamber_cooled_temp`, the one setting
you are expected to change, and the timing values the engine is built on: `loop_seconds`,
`report_minutes`, `status_seconds`, `stall_seconds`, `arrow_band` and `idle_margin_seconds`. Leave
the timing values alone unless you have a reason. The engine keeps its progress in `_COOLDOWN_VARS`.
Never write that macro by hand.
