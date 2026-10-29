# Troubleshooting

The phase banners, the progress lines and the temperature line are information (see
[How it works](HOW_IT_WORKS.md)). The messages below say something happened that you may need to act
on. In a message, `<name>` stands for a value that changes.

## A command refused to run

`START_COOLDOWN` and `COOLDOWN_SELECT` check everything first. When one of these appears, nothing
was started or changed.

| Message | What to do |
|---|---|
| `Klipper-Hardware-Controls is not installed. Include its settings, fans and chamber modules first. Cooldown not started.` | Install [Hardware Controls](https://github.com/IdleStep/Klipper-Hardware-Controls#install) and include its `hardware.cfg`. |
| `A cooldown is already running (phase <n>/5), so nothing was started. Run COOLDOWN_RESET first to start another.` | Run `COOLDOWN_RESET`, then start again. |
| `A cooldown is running, so the material was not selected. Run COOLDOWN_RESET first to change it.` | Run `COOLDOWN_RESET`, then select again. |
| `Unknown cooldown profile: <name>. Known profiles: <list>. Cooldown not started.` | Use one of the listed names. |
| `Invalid cooldown profile <name>: <reasons>. Cooldown not started.` | The profile's values are wrong. The message says which. See [Profile checks](HOW_IT_WORKS.md#profile-checks). |
| `chamber_cooled_temp in _COOLDOWN_SETTINGS must be a number. Cooldown not started.` | Fix the value in your `cooldown-local.cfg`. |
| `Invalid _COOLDOWN_SETTINGS: <reasons>. Cooldown not started.` | A timing setting is not a number or is out of range. The message says which. Fix it in your `cooldown-local.cfg` or remove the override. |
| `chamber_sensor in _HARDWARE_VARS has no temperature. Cooldown not started.` (or `bed_heater`) | The name is not a temperature device. Fix it in your `hardware_names.cfg`. |
| `Unknown material <name>, using the DEFAULT profile <profile>` | The material is not in `_COOLDOWN_MATERIALS`. Fix the spelling or add it. The `DEFAULT` profile was selected. |
| `Material <name> maps to profile <profile>, which is not in the profile table. Profile not changed.` | Your override maps a material to a profile that does not exist. |
| `materials in _COOLDOWN_MATERIALS must be a table of material names and profile names. Profile not changed.` | Your override replaced the material table with something that is not a table. |
| `The profile for this material has a quote mark, semicolon, hash sign or asterisk in its name, which is not allowed. Profile not changed.` | Rename the profile in your override. Use `A-Z`, `0-9` and `_`. |

## A cooldown started with a warning

| Message | What to do |
|---|---|
| `Ramp step of <n> s runs as <m> s because the loop ticks every <s> s` | Nothing, or change the profile's step time to a multiple of the tick. |
| `exhaust_fan_speed <speed> is below the fan minimum, so these fans run at their minimum instead: <fans>` | The fan would not turn at that speed. It runs at its `min_power` or `off_below`. |
| `Idle timeout kept at <n> s while the cooldown runs, then set to <m> s` | You set a shorter timeout during the cooldown. It applies when the heater is released. |

## A phase was skipped or changed

| Message | Meaning |
|---|---|
| `No chamber heater, skipping hold and ramp` | `chamber_heater` is empty or the heater is not configured. |
| `Chamber target <t>°C is below the ramp target <r>°C, skipping hold and ramp` | The chamber target was already lower than the ramp target when the cooldown started. |
| `Bed heater turned off (its target was <t>°C), the bed now cools with the chamber` | The rest phase released a bed target that was still on. |
| `No exhaust, external_pc or bed_fans fan configured, skipping exhaust` | None of the three fan roles names a configured fan. |

## The cooldown stopped

| Message | What to do |
|---|---|
| `Cooldown stopped: chamber, bed or fan settings were changed by hand (<what>). The rest of the cooldown is cancelled and the heaters and fans stay as you set them.` | Nothing. Heaters and fans stay as you set them. |
| `Cooldown stopped: the printer started printing` | A print started while the cooldown was running. |
| `Cooldown stopped: a value in _COOLDOWN_VARS is not valid. The heaters are off.` | Something wrote to `_COOLDOWN_VARS`, or a setting is not a number. The chamber and bed heaters were turned off. |
| `Cooldown stopped: the chamber or bed temperature cannot be read. The heaters are off.` | Check the sensors. The chamber and bed heaters were turned off. |
| `The cooldown loop last ran <n> s ago. If the printer was not busy, it has stopped. Run COOLDOWN_RESET to clear it.` | `COOLDOWN_STATUS` shows this when the loop has not ticked for 60 s (`stall_seconds`). A busy printer can cause it too. Run `COOLDOWN_RESET`. |
| `Cooldown complete` | Done. The heaters and all fans are off. |
| `Cooldown reset` | `COOLDOWN_RESET` stopped it, from your print start, the idle timeout or by hand. |

## Klipper reports an unknown command

- For `START_COOLDOWN` or another cooldown command: the
  `[include Klipper-Chamber-Cooldown/cooldown.cfg]` line is missing from `printer.cfg`, or Klipper
  was not restarted after adding it.
- For `RESPOND`: add a `[respond]` section to `printer.cfg`.

## Klipper reports an error about `SET_IDLE_TIMEOUT` at startup

Only one config can rename `SET_IDLE_TIMEOUT`. If another file of yours does, remove the
`[include idle_timeout_tracking.cfg]` line from `cooldown.cfg`. See
[Idle timeout](HOW_IT_WORKS.md#idle-timeout).
