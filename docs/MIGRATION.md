# Upgrading and migration

## From 1.x to 2.0

Two names changed in your local override files. Nothing else about the commands, the
profiles or the material map changed.

| In 1.x | In 2.0 |
|---|---|
| `[gcode_macro _COOLDOWN_VARS]` with `variable_chamber_cooled_temp` | `[gcode_macro _COOLDOWN_SETTINGS]` with `variable_chamber_cooled_temp` |
| `[gcode_macro _COOLDOWN_MATERIALS]` with `variable_filament_table` | the same macro with `variable_materials` |

If you do not change both in your `cooldown-local.cfg` the old values are ignored, and the
cooldown uses 35 °C and the shipped material table. There is no error. Also new in 2.0:

- A cooldown that stops because a value is invalid or a temperature cannot be read turns
  the chamber and bed heaters off.
- `START_COOLDOWN` says so when Klipper-Hardware-Controls is not installed.
- The timing values are settings in `_COOLDOWN_SETTINGS`; the defaults are the old behavior.

Update while the printer is idle. To roll back, check out `v1.1.0` and restore the two
names above.

## From the cooldown in Klipper-Configs

1. Install Hardware Controls first.
2. Remove the old helper includes before adding the Hardware Controls ones. Never load
   both: the macros would be defined twice.
3. Replace the old cooldown include with `Klipper-Chamber-Cooldown/cooldown.cfg`.
4. Keep local overrides outside both checkouts.
5. Back up the root config files, the integration files you change, the saved state and
   the installed revisions, then restart while the printer is idle.

How Klipper-Configs calls the cooldown:

- Material handling calls `COOLDOWN_SELECT`, guarded so it runs only when cooldown is
  installed, after its existing material fallback.
- Print start calls `COOLDOWN_RESET`, print end and cancel call `START_COOLDOWN`, and the
  idle timeout and KlipperScreen call `COOLDOWN_RESET`.
- The startup `DISABLE_SENSORS` delayed gcode stays in Klipper-Configs' common macro file.
  The `ENABLE_MOTION_SENSOR` callback it schedules lives in Hardware Controls.

The engine no longer matches the original tick for tick: the defects listed in the
[design notes](DESIGN.md) were fixed after the migration.

To roll back, restore the old root includes and every changed integration file together,
restart while the printer is idle and check that the original configuration loads. Keep
backups outside paths that active `[include]` patterns match.
