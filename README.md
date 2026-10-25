# Klipper Chamber Cooldown

Material-selected five-phase chamber cooldown for Klipper and Kalico:
**hold → ramp → rest → exhaust → chill**. This repository owns the engine, six
profiles and the material map. It has no dependency on Klipper-Configs.

Cooldown API: **version 1**. See the [changelog](CHANGELOG.md) and
[design decisions and known limits](docs/DESIGN.md).

## Install

Requires [Klipper-Hardware-Controls](https://github.com/IdleStep/Klipper-Hardware-Controls)
API 1 (its settings, fans and chamber modules) and `[respond]`. Device
definitions stay in your printer configuration. Clone both repositories under
`~/printer_data/config`, then include each module once:

```ini
[include Klipper-Hardware-Controls/settings.cfg]
[include Klipper-Hardware-Controls/fans.cfg]
[include Klipper-Hardware-Controls/chamber.cfg]
[include hardware-local.cfg]
[include Klipper-Chamber-Cooldown/cooldown.cfg]
[include cooldown-local.cfg]
```

Hardware Controls' `hardware.cfg` can replace its three individual modules.
Local override files live outside both checkouts and load after the defaults.

## Configuration

Cooldown finds devices through Hardware Controls' `_HARDWARE_VARS`
(`chamber_heater`, `chamber_sensor`, `bed_heater`, `exhaust_fan`, `bed_fans`,
`external_pc`). For a chamber with only a sensor, set `chamber_heater` to `""` and
`chamber_sensor` to the full object name, for example
`"temperature_sensor chamber"`; hold and ramp are then skipped.

The one user setting is the completion temperature, in
[`examples/cooldown-local.cfg`](examples/cooldown-local.cfg):

```ini
[gcode_macro _COOLDOWN_SETTINGS]
variable_chamber_cooled_temp: 35
```

`_COOLDOWN_SETTINGS` also holds the timing the engine is built on (`loop_seconds`,
`report_minutes`, `status_seconds`, `stall_seconds`, `arrow_band`,
`idle_margin_seconds`). Leave them unless you have a reason. The engine keeps its own
progress in `_COOLDOWN_VARS`; never write that macro by hand.

## Commands

| Command | Behavior |
|---|---|
| `COOLDOWN_SELECT MATERIAL=ASA` | Picks the profile mapped to the material; unknown materials get the table's `DEFAULT` (PASSIVE_ONLY) and a message. A blank material is `DEFAULT` without one. While a cooldown is running it only prints a message, so the running profile and `COOLDOWN_STATUS` stay correct. |
| `START_COOLDOWN` | Starts the selected profile (PASSIVE_ONLY when none was selected). `PROFILE=NAME` overrides the selection and may be typed in any case. An unknown profile reports the known profile names, and an invalid one reports what is wrong with it; neither starts. While a cooldown is running it prints a message and changes nothing; run `COOLDOWN_RESET` first to start another. |
| `COOLDOWN_STATUS` | Shows profile, phase number and name, and time in the phase. Adds a warning when the loop has not run for a minute (see Messages). |
| `COOLDOWN_RESET` | Stops the cooldown, clears the selection and restores an idle timeout the cooldown raised. Heaters and fans are left as they are. |

Select the material again after a reset. Runtime state is not kept across
restarts.

## How a cooldown runs

The loop runs every 5 seconds (`loop_seconds`). Each tick either stops the cooldown, moves to
the next phase, or advances the current one.

| Phase | What happens | Ends when |
|---|---|---|
| 1 HOLD | Chamber heater keeps its print target. | Hold time passes. Skipped when the profile has no hold. Without a chamber heater, or when the target is already below the ramp target, the cooldown goes straight to phase 3. |
| 2 RAMP | Target drops `cooldown_ramp_step_c` every `cooldown_ramp_step_seconds`, never below the ramp target. | Target reaches the ramp target. Skipped when the profile has none. |
| 3 REST | Chamber and bed heaters off; exhaust, external_pc and bed fans off if the rest is longer than 0. | Rest time passes. Skipped when the profile has no rest. |
| 4 EXHAUST | Exhaust, external_pc and bed fans set to the profile speed (0 when `exhaust_enable` is False). A speed above 0 that is below a fan's `min_power` (or `off_below`) is raised to that minimum for that fan. | On the next tick. |
| 5 CHILL | Waits; fans keep running. | Chamber and bed at or below `chamber_cooled_temp`. |

Every phase prints a numbered banner, so a cooldown always counts from 1/5 to
5/5. A phase the profile does not use says `skipped`.

At any phase, the cooldown **completes** once chamber and bed are at or below
`chamber_cooled_temp`: the chamber and bed heaters and every fan (exhaust,
external_pc, bed fans and the part fan, including any you set yourself) are
turned off. It **stops** without
touching heaters or fans if you change the chamber target, bed target, exhaust
or bed fan speed by hand, or a print starts (Klipper's `print_stats.state` becomes
`printing`; homing, probing and other moves do not stop it).

When hold, ramp and rest would outlast `[idle_timeout]`, START_COOLDOWN raises
the timeout for those phases and restores the previous value when the heater
is released. The previous value is the one you set with `SET_IDLE_TIMEOUT`
(`idle_timeout_tracking.cfg` remembers it, and a pause, resume or
`DISABLE_TIMEOUT` that sets one is covered too), otherwise the configured one.
A shorter timeout set while the cooldown has the longer one in force is applied
when the heater is released. The normal idle timeout still limits the exhaust
and chill phases.

Klipper counts the idle timeout from the last move, heater command or fan
command, not from the start of the cooldown (measured on Turbo: a heater or fan
command restarts the clock, writing a macro variable or `M400` does not). Every
phase change and every ramp step sends one, so the timeout only has to cover the
longest stretch between them. START_COOLDOWN still checks the whole cooldown, so
it raises the timeout sooner than strictly needed. A 60-minute hold at 46°C fits
Turbo's 4800 s without a raise (no `Timeout set` line), and the printer stays
`Ready` through it.

`idle_timeout_tracking.cfg` wraps `SET_IDLE_TIMEOUT` (`rename_existing`). Only one
config can do that: if another file of yours already renames it, remove the
`[include idle_timeout_tracking.cfg]` line from `cooldown.cfg`, and the cooldown
goes back to restoring the configured value.

## Profiles

| Profile | Hold | Ramp target | Rest | Exhaust | Materials |
|---|---:|---:|---:|---:|---|
| HOLD_120M_COOL_NO_EX | 120 min | 42°C | 0 | 0% | PA, PA6, PA6CF, PACF |
| HOLD_30M_COOL_EX | 30 min | 42°C | 0 | 100% | none (use `PROFILE=`) |
| HOLD_60M_COOL_EX | 60 min | 42°C | 0 | 100% | ABS, ABSCF, ASA, ASACF, ASAGF, PA12 |
| IMMEDIATE_EX | 0 | none | 0 | 100% | PLA, PLA+, PLACF |
| PASSIVE_ONLY | 0 | none | 0 | 0% | DEFAULT, PC, PCABS, PCABSCF, PCCF, PCTG, PETG, PETGCF, HIPS |
| REST_5M_THEN_EX | 0 | none | 5 min | 100% | TPU72D, TPU90A, TPU95A |

Ramping profiles step 1°C every 120 seconds. Field meanings and limits are
documented at the top of [`profiles.cfg`](profiles.cfg).

START_COOLDOWN refuses a ramp step under 0.1°C (a ramp needs one), a step time under
5 seconds, negative times, a negative ramp target and an exhaust speed outside 0.0 to
1.0. It also refuses a profile whose values are missing or are not numbers (a value
in quotes is text). Fractional minutes are honored (a 0.5 minute hold is 30 seconds).

The loop ticks every 5 seconds, so a ramp step time is rounded to the nearest 5
seconds (5 is the minimum) and START_COOLDOWN says so; the banner and the
idle-timeout estimate use the rounded time. The material map keeps Turbo's effective
behavior, including HIPS and PCTG falling back to PASSIVE_ONLY.

## Integrating with print macros

Add guarded calls to existing macros rather than replacing them, and never write
`_COOLDOWN_VARS` directly:

| Where | Call |
|---|---|
| Print start, before material selection | `COOLDOWN_RESET` |
| Material handling | `COOLDOWN_SELECT MATERIAL={material}` |
| After print end and cancel actions | `START_COOLDOWN` |
| Idle timeout and UI shutdown or preheat | `COOLDOWN_RESET` |

```jinja
{% if 'gcode_macro START_COOLDOWN' in printer %}
  START_COOLDOWN
{% endif %}
```

## Troubleshooting

The phase banners, the progress lines and the temperature line (`Chamber → 041.0/042.0 • Bed →
034.0/035.0 • Cycle 005`) are information. These messages say something happened that you may
need to act on:

| Message | What to do |
|---|---|
| `Klipper-Hardware-Controls is not installed. ... Cooldown not started.` | Install it and include its settings, fans and chamber modules (see Install). |
| `Unknown cooldown profile: NAME. Known profiles: ...` | Nothing was started. Use one of the listed names. |
| `Invalid cooldown profile NAME: ...` | Nothing was started. The profile's values are wrong; the message says which. |
| `chamber_cooled_temp in _COOLDOWN_SETTINGS must be a number.` | Fix the value in `cooldown-local.cfg`. |
| `chamber_sensor in _HARDWARE_VARS has no temperature.` (or `bed_heater`) | The name in `_HARDWARE_VARS` is not a temperature device. Fix it in `hardware-local.cfg`. |
| `A cooldown is already running (phase N/5), so nothing was started.` | Run `COOLDOWN_RESET` first to start another. |
| `A cooldown is running, so the material was not selected.` | Run `COOLDOWN_RESET` first to change it. |
| `Unknown material ASAA, using the DEFAULT profile PASSIVE_ONLY` | The material is not in `_COOLDOWN_MATERIALS`; fix the spelling or add it. |
| `Material ASA maps to profile NAME, which is not in the profile table.` | A local override maps a material to a profile that does not exist. The selection was not changed. |
| `materials in _COOLDOWN_MATERIALS must be a table ...` | A local override replaced the material table with something that is not a table. |
| `Ramp step of N s runs as M s because the loop ticks every 5 s` | The profile's step time is not a multiple of 5; it runs at the nearest one. |
| `exhaust_fan_speed 0.05 is below the fan minimum, so these fans run at their minimum instead: ...` | The fan would not turn at that speed; it runs at its `min_power` or `off_below`. |
| `Cooldown stopped: chamber, bed or fan settings were changed by hand (...)` | Heaters and fans stay as you set them; the rest of the cooldown is cancelled. |
| `Cooldown stopped: the printer started printing` | A print started while the cooldown was running. |
| `Cooldown stopped: a value in _COOLDOWN_VARS is not valid. The heaters are off.` | Something wrote to `_COOLDOWN_VARS` or a setting is not a number. The chamber and bed heaters were turned off. |
| `Cooldown stopped: the chamber or bed temperature cannot be read. The heaters are off.` | Check the sensors. The chamber and bed heaters were turned off. |
| `The cooldown loop last ran 270 s ago. ...` | The loop has stopped (or the printer was busy for a long time). Run `COOLDOWN_RESET`. |
| `Bed heater turned off (its target was 100°C), the bed now cools with the chamber` | The rest phase released a bed target that was still on. |
| `Cooldown complete` / `Cooldown reset` | Done, or stopped by `COOLDOWN_RESET` (from PRINT_START, the idle timeout or by hand). |

## Updates and rollback

Add [`examples/moonraker.conf`](examples/moonraker.conf) to `moonraker.conf`. It
follows tagged releases (`channel: stable`); use `channel: dev` to follow `main`.
Update while the printer is idle, keep overrides outside the checkout and record
the tested revisions of both repositories per printer. Cooldown API 1 works with
Hardware Controls API 1 from 1.0.0 on. Migration from the Klipper-Configs
cooldown is in [docs/MIGRATION.md](docs/MIGRATION.md).

## Tests

Check out Hardware Controls as `hardware-controls` beside this README (it
provides the shared test harness), then:

```sh
pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

- `tests/test_templates.py` simulates every profile and phase path.
- `tests/test_config_lint.py` checks the config files.
- `tests/test_klippy.py` runs `tests/klippy/*.gcode` in real Klipper and Kalico
  without hardware; it is skipped unless `KLIPPER_DIR`, `KLIPPY_DICT` and
  `KLIPPY_PYTHON` are set (see the CI workflow).

CI also runs the suite against Hardware Controls 1.0.0. None of this replaces a
real thermal run on the printer.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Report a safety problem as described in
[SECURITY.md](SECURITY.md).

## Style

Conventions for the config files, messages and tests, shared with
Klipper-Hardware-Controls and Klipper-Configs, are in
[Hardware Controls' docs/STYLE.md](https://github.com/IdleStep/Klipper-Hardware-Controls/blob/main/docs/STYLE.md).

## License

GPL-3.0.
