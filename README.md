# Klipper Chamber Cooldown

[![Template regression checks](https://github.com/IdleStep/Klipper-Chamber-Cooldown/actions/workflows/templates.yml/badge.svg)](https://github.com/IdleStep/Klipper-Chamber-Cooldown/actions/workflows/templates.yml)

Material-selected chamber cooldown for Klipper and Kalico: hold, ramp, rest, exhaust, chill.

After a print, the cooldown brings the chamber and bed down to a safe temperature in up to five
phases. The filament material picks a profile: how long the chamber heater holds its target, how
the target ramps down, and whether the exhaust fan runs. It ends by turning off the heaters and
fans. Changing a chamber target, a bed target or an exhaust or bed fan speed by hand cancels it.

```
🧊 Cooldown started with profile: HOLD_60M_COOL_EX
♨️ Cooldown phase 1/5 HOLD: keeping the chamber target for 60.0 min
📃 Chamber → 062.0/062.0  •  Bed → 100.0/100.0  •  Cycle 005
🤝 Hold complete
🧗 Cooldown phase 2/5 RAMP: lowering the chamber target 1.0°C every 120 s to 42.0°C
🏁 Ramp target reached
⏳ Cooldown phase 3/5 REST: chamber heater off, rest skipped, profile has no rest
💨 Cooldown phase 4/5 EXHAUST: fans to 1.0
🐌 Cooldown phase 5/5 CHILL: waiting for chamber and bed at or below 35°C
❄️ Cooldown complete
```

The console output above is abridged. [How it works](docs/HOW_IT_WORKS.md) describes each phase.

## Requirements

- Klipper or Kalico, with `[respond]` in your configuration.
- [Klipper-Hardware-Controls](https://github.com/IdleStep/Klipper-Hardware-Controls) 2.0.0 or
  later. It provides the chamber heater and fan commands and the names of your devices.

## Install

1. **Install Hardware Controls.** Follow its
   [install steps](https://github.com/IdleStep/Klipper-Hardware-Controls#install): include its
   `hardware.cfg`, then name your devices in your own `hardware_names.cfg`. The devices Cooldown
   needs are listed under [Configure](#configure).
2. **Clone this repository** next to your `printer.cfg`:

   ```sh
   cd ~/printer_data/config
   git clone https://github.com/IdleStep/Klipper-Chamber-Cooldown.git
   ```

3. **Include it** in `printer.cfg`, after the Hardware Controls lines:

   ```ini
   [include Klipper-Chamber-Cooldown/cooldown.cfg]
   [include cooldown-local.cfg]
   ```

   `cooldown-local.cfg` is your own file, outside the checkout, for overrides. Copy
   [`examples/cooldown-local.cfg`](examples/cooldown-local.cfg) to start it, or leave the line out.
4. **Add the update entry** to `moonraker.conf`
   (also in [`examples/moonraker.conf`](examples/moonraker.conf)):

   ```ini
   [update_manager Klipper-Chamber-Cooldown]
   type: git_repo
   channel: stable
   path: ~/printer_data/config/Klipper-Chamber-Cooldown
   origin: https://github.com/IdleStep/Klipper-Chamber-Cooldown.git
   primary_branch: main
   is_system_service: False
   managed_services: klipper
   ```

5. Restart Klipper.

## Configure

Cooldown reads these roles from `_HARDWARE_VARS`, which you set in your `hardware_names.cfg`.
A role left empty is skipped.

| Role | Used for |
|---|---|
| `chamber_heater` | Hold and ramp targets. Without it, hold and ramp are skipped. |
| `chamber_sensor` | Chamber temperature when there is no heater, as a full object name such as `"temperature_sensor chamber"`. |
| `bed_heater` | Bed temperature. The default `"heater_bed"` is right for most printers. |
| `exhaust_fan`, `external_pc`, `bed_fans` | Fans that run in the exhaust phase. |

Set `chamber_heater` or `chamber_sensor`. With neither, the chamber reads as 0°C and only the
bed decides when the cooldown completes.

The one setting is the completion temperature. Put it in your `cooldown-local.cfg`:

```ini
[gcode_macro _COOLDOWN_SETTINGS]
variable_chamber_cooled_temp: 35
```

## Usage

| Command | What it does |
|---|---|
| `COOLDOWN_SELECT MATERIAL=ASA` | Picks the profile for a material. An unknown material gets the `DEFAULT` profile. |
| `START_COOLDOWN` | Starts the selected profile, or `PASSIVE_ONLY` when none was selected. `PROFILE=NAME` overrides the selection. |
| `COOLDOWN_STATUS` | Shows the profile, the phase and the time in the phase. |
| `COOLDOWN_RESET` | Stops the cooldown and clears the selection. Heaters and fans stay as they are. |

Select the material again after a reset. Nothing is kept across a Klipper restart.

To run it automatically, add guarded calls to your print macros:

| Where | Call |
|---|---|
| Print start, before material selection | `COOLDOWN_RESET` |
| Material handling | `COOLDOWN_SELECT MATERIAL={material}` |
| Print end and cancel | `START_COOLDOWN` |
| Idle timeout and preheat macros | `COOLDOWN_RESET` |

```jinja
{% if 'gcode_macro START_COOLDOWN' in printer %}
  START_COOLDOWN
{% endif %}
```

## Profiles and materials

| Profile | Hold | Ramp to | Rest | Exhaust | Materials |
|---|---:|---:|---:|---:|---|
| `HOLD_120M_COOL_NO_EX` | 120 min | 42°C | - | off | PA, PA6, PA6CF, PACF |
| `HOLD_30M_COOL_EX` | 30 min | 42°C | - | 100% | none, use `PROFILE=` |
| `HOLD_60M_COOL_EX` | 60 min | 42°C | - | 100% | ABS, ABSCF, ASA, ASACF, ASAGF, PA12 |
| `IMMEDIATE_EX` | - | - | - | 100% | PLA, PLA+, PLACF |
| `PASSIVE_ONLY` | - | - | - | off | DEFAULT, HIPS, PC, PCABS, PCABSCF, PCCF, PCTG, PETG, PETGCF |
| `REST_5M_THEN_EX` | - | - | 5 min | 100% | TPU72D, TPU90A, TPU95A |

Ramping profiles lower the chamber target by 1°C every 120 s.

To change a profile or the material map, copy `variable_profiles` from
[`profiles.cfg`](profiles.cfg) or `variable_materials` from [`materials.cfg`](materials.cfg) into
your `cooldown-local.cfg` and edit the copy. The later definition replaces the whole table, so keep
every entry you still want. The top of `profiles.cfg` explains each field.

## More

- [How it works](docs/HOW_IT_WORKS.md): phases, completion and stop rules, idle timeout,
  profile checks.
- [Troubleshooting](docs/TROUBLESHOOTING.md): every message you may need to act on.
- [Design decisions and known limits](docs/DESIGN.md)
- [Upgrading and migration](docs/MIGRATION.md)
- [Changelog](CHANGELOG.md)

## Updating

Update while the printer is idle, from Moonraker or with `git pull` in the checkout. The
`stable` channel follows tagged releases; use `channel: dev` to follow `main`. To roll back,
check out the previous tag. Cooldown API 2 works with Hardware Controls 2.0.0 and later.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Report a safety problem as described in
[SECURITY.md](SECURITY.md).

## License

GPL-3.0.
