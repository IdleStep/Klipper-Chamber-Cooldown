# Design decisions and known limits

## What the tests pin down

- Every path into phase 3 turns the chamber heater off, and so does completion, so no profile
  can finish with the heater still on.
- Each tick performs one transition or one increment, and every transition goes through
  `_COOLDOWN_ENTER_PHASE`.
- START_COOLDOWN raises the idle timeout to cover hold, ramp and rest when needed and puts the
  configured value back on phase 3, completion or reset.
- Entering phase 3 turns the exhaust fan off when the rest is longer than 0, and
  `exhaust_enable: False` runs phase 4 at speed 0 (a missing key counts as True).
- START_COOLDOWN refuses an invalid profile and invalid settings (a value that is not a number,
  a `loop_seconds` below 1) instead of starting a loop that would raise. Ramp steps never go
  below the ramp target.
- A tick that finds a non-numeric state value or a phase outside 1-5 stops the cooldown, turns
  the heaters off and says so.
- Both report arrows compare readings with the displayed target.

## By design

- COOLDOWN_RESET stops automation, clears the selection and restores an extended
  idle timeout, but leaves heaters and fans alone. PRINT_START and UI preheats call
  it after setting their own targets. Completion turns the chamber heater, the bed
  heater and every fan (the part fan and any fan you set by hand included) off.
- Changing the chamber target, bed target, exhaust fan speed or bed fan speed by
  hand cancels the whole cooldown, including turning the chamber heater off to
  end a hold early. The stop message names what changed. Nothing is skipped
  ahead to the rest phase, and the heaters and fans stay as you set them.
- Report arrows show above / near / below the displayed target, not a
  temperature trend.
- A phase the profile does not use still prints its numbered banner, marked
  `skipped`, so the user sees every phase from 1/5 to 5/5.
- The exhaust and chill phases have no separate deadline: the normal idle timeout
  applies once the heater is released, counted from the fan command that starts
  the exhaust phase. A chill that takes longer than the timeout ends silently
  (the idle gcode turns the fans and heaters off and calls `COOLDOWN_RESET`).
- HIPS and PCTG keep their PASSIVE_ONLY fallback from Turbo's old retraction table.
  Changing intended profiles is separate work.
- The print check reads `print_stats.state`, which only a file print sets (a
  printer without a `print_stats` object has no check). It replaced a test of
  `idle_timeout.state`, which can read `Printing` after a move, dwell or homing,
  not only during a print. Klipper-Configs' PRINT_START calls `COOLDOWN_RESET`
  first, so the check matters only for a print started some other way.
- The cooldown cannot read the idle timeout in force (a macro only sees the
  configured `[idle_timeout]` value). `idle_timeout_tracking.cfg` (included by
  `cooldown.cfg`) wraps `SET_IDLE_TIMEOUT` and remembers the last value set by
  hand, so a timeout from `DISABLE_TIMEOUT`, a pause or `SET_IDLE_TIMEOUT` is
  respected: START extends only when the cooldown needs more than that value,
  a shorter value set during the hold and ramp (a RESUME) waits until the heater is
  released, and phase 3, completion and reset hand the remembered value back.
  The remembered value, like the timeout, is lost when Klipper restarts. Only
  one config can rename `SET_IDLE_TIMEOUT`: if yours already does, remove the
  `[include idle_timeout_tracking.cfg]` line from `cooldown.cfg`. The cooldown then
  works from the configured value as before, replacing a timeout you set yourself
  and sometimes shortening a longer one during the hold and ramp.
- Completion needs the bed reading at or below `chamber_cooled_temp`. Phase 3
  turns the bed heater off (with a `Bed heater turned off` message) so a bed
  target left on after the print cannot stop the cooldown from completing. The
  bed is held on through the hold and ramp. A bed you switch back on by hand
  later cancels the cooldown, as any bed target change does.
- `UPDATE_DELAYED_GCODE ID=_COOLDOWN_LOOP DURATION=0` typed by hand stops the
  loop without resetting the cooldown, so it still shows a running phase and the
  heater keeps its target. Use `COOLDOWN_RESET` to stop it. COOLDOWN_STATUS warns
  when the loop has not run for a minute (the printer clock it compares comes
  from `toolhead.estimated_print_time`); a busy printer can trigger the warning
  too.
- Profile and material names should be `A-Z`, `0-9` and `_`. A quote mark in a
  profile name is refused, because the name is stored with
  `SET_GCODE_VARIABLE` and a quote breaks that command. Mainline Klipper also
  cuts a `;`, `#` or `*` out of a command line before any macro sees it, even
  inside quotes (Kalico keeps them), so such a name could not be typed there.
  START_COOLDOWN and COOLDOWN_SELECT therefore refuse a name with a quote mark,
  semicolon, hash sign or asterisk, and show those characters as `?` in their
  messages.

Isolated template checks do not establish full thermal or firmware equivalence.
