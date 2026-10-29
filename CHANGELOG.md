# Changelog

Versions follow the cooldown API: the major version changes when a public command, its
parameters, a profile or material name, or a variable that a local override file sets
(`chamber_cooled_temp`, the profile and material tables) changes incompatibly. Changes
inside the engine and its messages are minor or patch releases.

## [Unreleased]

### Changed
- The README is shorter and follows the order install, configure, use. Hardware Controls is one
  prerequisite step that links to its own install steps, and only this repository's two
  includes are shown. The phase rules, the idle timeout notes and the profile checks moved to the
  new `docs/HOW_IT_WORKS.md`, and the message table to the new `docs/TROUBLESHOOTING.md`, which now
  also lists the settings refusal, the skip notes and the idle timeout note. The test layout moved
  to `CONTRIBUTING.md`. Wording that referred to other repositories was removed from `docs/DESIGN.md`.

## [2.1.1] - 2026-10-28

Requires Hardware Controls 2.0.0 or later.

### Changed
- Tests: `tests/test_templates.py` (1259 lines, 98 tests) is split into one file per topic; it
  keeps the shared simulated printer and helpers, which Klipper-Configs imports. No test changed.
- A description in `idle_timeout_tracking.cfg` and a comment in `profiles.cfg` fit in 100
  columns, as the shared lint now checks.

### Fixed
- The refusal for a setting or profile value that is not a number reads correctly for one key
  (`arrow_band must be a number`) and for several (`report_minutes, status_seconds must each be
  a number`); it said `must be numbers` for both.

## [2.1.0] - 2026-10-27

Requires Hardware Controls 2.0.0 or later.

### Fixed
- `START_COOLDOWN` refuses settings the loop would divide by or choke on: an `arrow_band`,
  `idle_margin_seconds`, `loop_seconds`, `report_minutes`, `status_seconds` or `stall_seconds`
  that is not a number, a `loop_seconds` below 1 or not whole, a negative `arrow_band` or
  `idle_margin_seconds`, and a `status_seconds`, `stall_seconds` or `report_minutes` times 60
  below `loop_seconds`. They used to start the cooldown (raising the idle timeout and keeping
  the heater at its hold target), and the first tick raised `ZeroDivisionError`, which stops a
  delayed gcode for good. It says `Invalid _COOLDOWN_SETTINGS: ...` and starts nothing.

### Changed
- The README says Cooldown API 2, as the release is 2.0.0. `docs/DESIGN.md` opens with what the
  tests pin down instead of a table of former defects, and the CHANGELOG has one Changed heading
  per version, dates and compare links.
- The README requires Hardware Controls 2.0.0 or later, where the roles are off until a
  printer's own copy of `hardware_names.cfg` names its devices, and the install steps follow.
  Cooldown itself is unchanged. The checks also run against Hardware Controls 2.0.0 instead of 1.0.0.
- SECURITY.md asks for a public issue instead of a private report.
- The checks take the test harness from the latest `main` of Hardware Controls instead of a
  pinned commit. The oldest supported release and the firmware revisions stay pinned.

## [2.0.0] - 2026-10-25

Requires Hardware Controls 1.0.0 or later. Upgrade steps are in
[docs/MIGRATION.md](docs/MIGRATION.md).

### Changed
- Breaking: `chamber_cooled_temp` moved from `_COOLDOWN_VARS` to the new `_COOLDOWN_SETTINGS`.
  `_COOLDOWN_VARS` is now only the engine's own state.
- Breaking: the material table variable `filament_table` of `_COOLDOWN_MATERIALS` is now
  `materials`. A local file that still sets the old names is ignored without an error.
  1.1.0 renamed the profile table the same way; under the rule above that was a
  major version too.
- The timing the engine is built on is set in `_COOLDOWN_SETTINGS`: `loop_seconds`,
  `report_minutes`, `status_seconds`, `stall_seconds`, `arrow_band` and
  `idle_margin_seconds`. The defaults are the old values (5 s, 2 min, 25 s, 60 s,
  2 °C, 600 s).
- The HOLD and exhaust banners use `♨️` and `💨`; the old symbols are Unicode 15 and
  show as boxes on older browsers and KlipperScreen fonts.
- README: the message table is now a troubleshooting table of the messages that need
  an action. `docs/KNOWN_ISSUES.md` is `docs/DESIGN.md`, and `docs/MIGRATION.md`
  covers upgrading and no longer carries the migration's working notes.

### Fixed
- A cooldown that stops because a state value is invalid or a chamber or bed
  temperature cannot be read now turns the chamber and bed heaters off, and says so
  (`The heaters are off.`). It used to leave the heater at its hold target.
- The loop checks `exhaust_fan_speed` and `cooldown_ramp_step_seconds` along with the
  other numbers it needs.
- `START_COOLDOWN` says `Klipper-Hardware-Controls is not installed` instead of
  failing with a template error.

## [1.1.0] - 2026-10-25

Requires Hardware Controls 1.0.0 or later.

### Fixed
- The chamber heater is turned off on every path into the rest phase and on
  completion; PASSIVE_ONLY, REST_5M_THEN_EX, IMMEDIATE_EX and skipped holds used
  to leave it heating so the cooldown never finished.
- One phase transition or increment per loop tick; skips no longer overwrite
  each other.
- Idle timeout is raised for long hold/ramp phases and restored afterwards.
- Passive rest turns the exhaust off; `exhaust_enable` is honored.
- Invalid profiles are refused at start; ramp steps never overshoot.
- A profile with several problems lists them all in one `Invalid cooldown
  profile` line. They were joined with `;`, which Klipper and Kalico treat as
  the start of a comment, so the message was cut off.
- Chamber progress arrow works, and the bed arrow compares with the displayed
  bed value (target or `chamber_cooled_temp`), as the chamber arrow does.
- START_COOLDOWN refuses a `chamber_cooled_temp` that is not a number (text,
  empty or a list). It used to start, raise the idle timeout and then raise on
  the first tick, which left the heater at its hold target with the loop dead
  until the idle timeout. A tick that finds a non-numeric state value or a phase
  outside 1-5 now stops the cooldown with `Cooldown stopped: a value in
  _COOLDOWN_VARS is not valid`.
- Banner 2/5 is printed when hold and ramp are skipped (no chamber heater, or a
  start target below the ramp target). The cooldown used to print 1/5, 3/5, 4/5
  and 5/5 on those paths; it now says `Cooldown phase 2/5 RAMP: skipped, no hold
  or ramp to run`.
- Phase 4 counts `bed_fans`. A printer with only bed fans was told `No exhaust
  or external_pc fan configured, skipping exhaust` and its bed fans were never
  set; the message now reads `No exhaust, external_pc or bed_fans fan
  configured, skipping exhaust` and appears only when none of the three exists.
- `exhaust_enable` in a profile must be `True` or `False` (`1` and `0` and a
  missing key work as before). Text such as `"False"` counted as true, so the
  fans ran at full speed; text and `None` are now refused with `exhaust_enable
  must be True or False`.
- Profile values must be present and numeric. `chamber_hold_minutes`,
  `passive_rest_minutes`, `chamber_target_temp`, `cooldown_ramp_step_c`,
  `cooldown_ramp_step_seconds` and `exhaust_fan_speed` used to be coerced
  silently: text or `None` read as 0 (a skipped phase, or fans set to 0), and a
  missing key raised a template error. START_COOLDOWN now refuses them in one
  `Invalid cooldown profile NAME: ... must be numbers` line. Text values such as
  `"60"`, which were accepted before, are refused too. The shipped profiles use
  numbers and are unaffected.
- Fractional hold and rest minutes are honored. They were truncated, so a hold
  of 0.5 minutes was no hold at all.
- A chamber with only a sensor has no tracked target. Changing
  `chamber_cooled_temp` during the cooldown no longer stops it with `changed by
  hand`.
- START_COOLDOWN refuses a `chamber_sensor` (when there is no chamber heater) or
  a `bed_heater` that has no `temperature`, which only happens when
  `_HARDWARE_VARS` names the wrong object. A tick that finds a reading that is
  not a number stops the cooldown with `Cooldown stopped: the chamber or bed
  temperature cannot be read`; the tick used to raise and strand the loop.
- A profile name with a quote mark (`O'NEIL`) is refused by START_COOLDOWN with
  `profile names cannot contain quote marks`, and COOLDOWN_SELECT refuses to
  store one. START used to fail half way through, after it had raised the idle
  timeout.
- COOLDOWN_SELECT trims whitespace around the material. `MATERIAL=" ASA"`
  silently selected the DEFAULT profile.
- A profile with a negative `chamber_target_temp` is refused. It was read as "no
  ramp".
- A ramping profile with `cooldown_ramp_step_c` under 0.1 is refused. A step of
  0.01 made a 44-hour ramp and raised the idle timeout to match.

### Changed
- `START_COOLDOWN PROFILE=` accepts a profile name in any case (materials
  already did), and `Unknown cooldown profile` now lists the known profiles. A
  `"` in the typed name is shown as `'`; it used to make the message itself fail
  with `Malformed command`.
- A ramp step time that is not a multiple of 5 seconds is rounded to the nearest
  5 (the loop ticks every 5 seconds), and START_COOLDOWN prints `Ramp step of 7 s
  runs as 5 s because the loop ticks every 5 s`. It used to run at the next
  lower multiple while the RAMP banner and the idle-timeout estimate used the
  requested time. A step time under 5 seconds is still refused, and a profile
  without a ramp is left alone.
- The check for a new print reads `print_stats.state` (`printing`) instead of
  `idle_timeout.state` with a five-tick guard. `idle_timeout` can read `Printing`
  after a move, dwell or homing, so a `G4 P30000` or a `G28` during the chill
  phase could stop the cooldown as if a print had started. The message is
  unchanged, and a printer without `print_stats` has no check.
- A profile fan speed above 0 but under a fan's `min_power` (or `off_below`) is
  raised to that minimum for that fan, and START_COOLDOWN prints `exhaust_fan_speed
  0.05 is below the fan minimum, so these fans run at their minimum instead:
  exhaust_fan (0.2)`. Mainline Klipper treats a speed under `off_below` as off. The
  shipped profiles use 0.0 and 1.0 and are unaffected.
- COOLDOWN_STATUS warns when a phase is running but the loop has not ticked for
  over a minute (`The cooldown loop last ran 270 s ago ...`), which is what
  `UPDATE_DELAYED_GCODE ID=_COOLDOWN_LOOP DURATION=0` or a stalled loop looks
  like. Each tick and START record `toolhead.estimated_print_time` in the new
  `last_tick` variable for it.
- A rest longer than 0 turns off the external_pc and bed fans as well as the
  exhaust. Only the exhaust used to stop, so the chamber was not still while it
  rested. Phase 4 still sets all three to the profile speed. The only shipped
  profile with a rest is REST_5M_THEN_EX.
- Completion also turns the bed heater off (when its target is above 0), so a
  finished cooldown leaves no heater on. It already turned off the chamber heater
  and every fan, including the part fan and fans you set by hand.
- New `idle_timeout_tracking.cfg`, included by `cooldown.cfg`, wraps
  `SET_IDLE_TIMEOUT` and remembers the timeout set by hand
  (`_COOLDOWN_VARS user_idle_timeout`). START extends from that value, a shorter
  value set during the hold and ramp is held back until the heater is released
  (`Idle timeout kept at N s while the cooldown runs, then set to M s`), and phase
  3, completion and reset put the remembered value back. Before, they wrote the
  configured value, so `DISABLE_TIMEOUT` (999999) and a pause (43200) were
  replaced by 4800. Remove the include line if another config renames
  `SET_IDLE_TIMEOUT`.
- Phase 3 REST turns the bed heater off when its target is above 0 and says so
  (`Bed heater turned off (its target was 100°C), the bed now cools with the
  chamber`). A bed target left on after the print used to keep CHILL from ever
  completing. The bed stays on through HOLD and RAMP.
- The `changed by hand` stop names what changed (`chamber target`, `bed target`,
  `exhaust fan speed`, `bed fans speed`) and says the rest of the cooldown is
  cancelled and the heaters and fans stay as set. The line starts as before.
- COOLDOWN_SELECT says `Unknown material ASAA, using the DEFAULT profile
  PASSIVE_ONLY` when the material is not in the table. A typo used to select
  DEFAULT without a word. A blank `MATERIAL=` still selects DEFAULT silently.
- COOLDOWN_SELECT refuses a material that maps to a profile missing from the
  profile table (`Material ASA maps to profile NAME, which is not in the profile
  table. Profile not changed.`). A bad local override used to be selected and
  failed at START_COOLDOWN, after the print.
- A profile name with a `;`, `#` or `*` is refused like one with a quote mark
  (`profile names cannot contain quote marks, semicolons, hash signs or
  asterisks`). Mainline Klipper cuts those characters out of a command line, and
  a `;` cut the refusal message itself. Messages show them as `?`.
- COOLDOWN_SELECT reports a material table that is not a table (a list, text or
  nothing) and leaves the selection alone. It used to raise `Error evaluating`,
  which aborted the macro that called it, and so the print start.
- COOLDOWN_SELECT during a running cooldown prints `A cooldown is running, so the
  material was not selected` and changes nothing. It used to overwrite the
  profile name, so COOLDOWN_STATUS showed the wrong profile and a second
  `START_COOLDOWN` started it.
- START_COOLDOWN during a running cooldown prints `A cooldown is already running
  (phase 1/5), so nothing was started` and changes nothing. A second START used
  to print `Cooldown started` again, restart the hold from the beginning and
  record the heaters and fans as they were mid-run. Run `COOLDOWN_RESET` first to
  start another.
- COOLDOWN_RESET prints `Cooldown reset` when it stops a running cooldown. The
  idle timeout or a print macro could end a cooldown without any message.
  Nothing is printed when no cooldown was running, and the cooldown's own stops
  and completion pass `QUIET=1`, so they still print one line.
- The phase 4 banner names each fan's speed when they differ
  (`EXHAUST: exhaust_fan to 0.2, external_pc to 0.1`). With a fan minimum it
  used to show the exhaust fan's speed for all of them.
- Clearer messages; COOLDOWN_STATUS shows the phase name and time in phase.
- A phase the profile does not use still prints its numbered banner, marked
  skipped (`Cooldown phase 2/5 RAMP: skipped, profile has no ramp`), instead of
  zero durations followed by `Hold complete` or `skipping ramp`.
- Internal names: `_CHAMBER_SET_TARGET` is now `_COOLDOWN_SNAPSHOT`, and its
  recorded values are `seen_*` variables in `_COOLDOWN_VARS`.
- The profile table is `_COOLDOWN_PROFILES.profiles` (was `filament_table`). A
  local file that overrides the profile table must use the new name.
- COOLDOWN_SELECT falls back to the material table's `DEFAULT`.
- Moonraker example follows tagged releases.
- The repository is renamed Klipper-Chamber-Cooldown (was
  Klipper-CHAMBER_COOLDOWN). Clone it into
  `~/printer_data/config/Klipper-Chamber-Cooldown` and include
  `Klipper-Chamber-Cooldown/cooldown.cfg`. GitHub redirects the old URL.
- The Moonraker example names its section after the repository:
  `[update_manager Klipper-Chamber-Cooldown]`.
- Code, comments, tests and docs tidied, with no behavior change. Conventions are in
  Hardware Controls' `docs/STYLE.md`.
- The two skip messages (`No chamber heater, skipping hold and ramp` and the
  `below the ramp target` line) use the note emoji instead of a lone arrow.
- Tests use Hardware Controls' shared harness, lint the configs, run in real
  Klipper and Kalico, and run against Hardware Controls 1.0.0.

## [1.0.0] - 2026-10-25

Turbo's five-phase cooldown migrated from Klipper-Configs, behavior preserved.

[Unreleased]: https://github.com/IdleStep/Klipper-Chamber-Cooldown/compare/v2.1.1...HEAD
[2.1.1]: https://github.com/IdleStep/Klipper-Chamber-Cooldown/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/IdleStep/Klipper-Chamber-Cooldown/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/IdleStep/Klipper-Chamber-Cooldown/compare/v1.1.0...v2.0.0
[1.1.0]: https://github.com/IdleStep/Klipper-Chamber-Cooldown/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/IdleStep/Klipper-Chamber-Cooldown/tree/v1.0.0
