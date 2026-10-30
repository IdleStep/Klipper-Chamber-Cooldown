# Klipper Chamber Cooldown

[![Template regression checks](https://github.com/IdleStep/Klipper-Chamber-Cooldown/actions/workflows/templates.yml/badge.svg)](https://github.com/IdleStep/Klipper-Chamber-Cooldown/actions/workflows/templates.yml)

Five-phase chamber cooldown for Klipper and Kalico, chosen by filament material.

After a print, `START_COOLDOWN` brings the chamber and bed down in five phases: **hold** the
chamber target, **ramp** it down, **rest** with the heaters off, run the **exhaust** fans, and
**chill** until both are at or below 35°C (the default). The filament material picks a profile,
which decides how long the hold lasts, how the ramp goes and whether the exhaust runs. A phase the
profile does not use is skipped. At the end the cooldown turns off the heaters and fans. Changing
a chamber target, a bed target or an exhaust or bed fan speed by hand cancels it.

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

The console output above is shortened: the progress and temperature lines between the phases are
left out. [How it works](docs/HOW_IT_WORKS.md) describes each phase.

## Requirements

- Klipper or Kalico, with a `[respond]` section in your `printer.cfg`. It lets macros print to
  the console, which is how the cooldown reports what it does.
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

   `cooldown-local.cfg` is your own file for overrides, next to your `printer.cfg` and outside
   the checkout. Copy [`examples/cooldown-local.cfg`](examples/cooldown-local.cfg) there to start
   it, or leave the line out.
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

5. Restart Moonraker and Klipper.

## Configure

Cooldown uses these roles of `_HARDWARE_VARS`. You set them in your own `hardware_names.cfg`; a
role left empty is skipped.

Roles that take several devices, as a name, a comma-separated string or a list (this needs
Hardware Controls 3.4.0 or later; an older version reads only a single name):

| Role | Used for |
|---|---|
| `chamber_heater` | The heaters whose target the hold keeps and the ramp lowers. The cooldown reads the first one that exists, so list the one that measures the chamber first. Without it, hold and ramp are skipped. |
| `exhaust_fan`, `external_pc`, `bed_fans` | The fans that run in the exhaust phase. Every fan of a role gets the same speed. |

Roles that take one device, a single name:

| Role | Used for |
|---|---|
| `chamber_sensor` | The chamber temperature when there is no heater, as a full object name such as `"temperature_sensor chamber"`. |
| `bed_heater` | The bed temperature. The rest phase turns the bed heater off. The default `"heater_bed"` is right for most printers. |

Set `chamber_heater` or `chamber_sensor`. With neither, the cooldown skips hold and ramp, warns
when it starts and waits for the bed only. For example, for a printer with a
`[heater_generic chamber]` and a `[fan_generic exhaust_fan]`:

```ini
[gcode_macro _HARDWARE_VARS]
variable_chamber_heater: "chamber"
variable_exhaust_fan: "exhaust_fan"
```

With a second exhaust fan, name both. The two lines mean the same:

```ini
variable_exhaust_fan: "exhaust_fan, filter_fan"
variable_exhaust_fan: ["exhaust_fan", "filter_fan"]
```

[How it works](docs/HOW_IT_WORKS.md#several-devices-in-one-role) says how the cooldown treats
several devices.

The one Cooldown setting is the completion temperature (default 35°C). The chamber and the bed
must both reach it. Put it in your `cooldown-local.cfg`:

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

While a cooldown runs, `COOLDOWN_SELECT` and `START_COOLDOWN` print a message and change nothing.
Run `COOLDOWN_RESET` first. Select the material again after a reset. Nothing is kept across a
Klipper restart.

To test the install, run `COOLDOWN_SELECT MATERIAL=ASA` and `START_COOLDOWN` on a cold printer. It
completes within seconds, because the chamber and bed are already at or below 35°C.

To run it automatically, add calls to your print macros:

| Where | Call |
|---|---|
| Print start, before material selection | `COOLDOWN_RESET` |
| Material handling | `COOLDOWN_SELECT MATERIAL={material}` |
| Print end and cancel | `START_COOLDOWN` |
| Idle timeout and preheat macros | `COOLDOWN_RESET` |

Call `COOLDOWN_RESET` after the macro sets its own heater targets. Guard every call like this, so
the macro still works when Cooldown is not installed:

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

Hold is how long the chamber heater keeps its print target. Ramp to is the chamber target the ramp
lowers it to, by 1°C every 120 s. Rest is a pause with the heaters and fans off before the exhaust.
Exhaust is the fan speed. A dash means the profile skips that phase. The material name is not case
sensitive, and a blank or unknown material uses `DEFAULT`.

To change a profile or the material map, copy `variable_profiles` from
[`profiles.cfg`](profiles.cfg) or `variable_materials` from [`materials.cfg`](materials.cfg) into
your `cooldown-local.cfg` and edit the copy. The later definition replaces the whole table, so keep
every entry you still want. The top of `profiles.cfg` explains each field.

## More

- [How it works](docs/HOW_IT_WORKS.md): phases, completion and stop rules, idle timeout,
  profile checks.
- [Troubleshooting](docs/TROUBLESHOOTING.md): every message you may need to act on.
- [Design decisions and known limits](docs/DESIGN.md)
- [Changelog](CHANGELOG.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Report a safety problem as described in
[SECURITY.md](SECURITY.md).

## License

GPL-3.0.
