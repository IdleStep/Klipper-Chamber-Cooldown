"""Cooldown under real Klipper and Kalico (batch mode, no hardware).

Uses Hardware Controls' runner and test printer (tests/klippy_batch.py,
tests/klippy/printer.cfg). Timers never fire in batch mode, so the
_COOLDOWN_LOOP body is also defined as TEST_COOLDOWN_TICK for scripts to call.
Scripts set chamber_cooled_temp below zero because heaters read 0°C here.
tests/klippy_override/ runs against a printer whose local file copies both tables, to show
that the later definition replaces the whole table. tests/klippy_several/ runs against a printer
whose roles name several devices.
"""
import pathlib
import unittest

import test_templates
from klippy_batch import SUPPORT_DIR, delayed_gcode_as_macro, run_script_files
from klipper_sim import HW_ROOT

SCRIPTS = pathlib.Path(__file__).resolve().parent / 'klippy'
OVERRIDE_SCRIPTS = pathlib.Path(__file__).resolve().parent / 'klippy_override'
SEVERAL_SCRIPTS = pathlib.Path(__file__).resolve().parent / 'klippy_several'

# What a user's cooldown-local.cfg holds after copying both tables and editing them.
LOCAL_OVERRIDE = '''
[gcode_macro _COOLDOWN_PROFILES]
variable_profiles:
  {
    "MY_PROFILE": {
      "chamber_hold_minutes":       1,
      "chamber_target_temp":        0,
      "cooldown_ramp_step_c":       0,
      "cooldown_ramp_step_seconds": 0,
      "passive_rest_minutes":       0,
      "exhaust_enable":             False,
      "exhaust_fan_speed":          0.0
    }
  }

[gcode_macro _COOLDOWN_MATERIALS]
variable_materials:
  {
    "DEFAULT": "MY_PROFILE",
    "XYZ":     "MY_PROFILE"
  }
'''

# Roles that name several devices, as a comma-separated string with a name that matches nothing.
SEVERAL_DEVICES = '''
[gcode_macro _HARDWARE_VARS]
variable_chamber_heater: "missing_heater, chamber"
variable_exhaust_fan: "exhaust_fan, external_pc, missing_fan"
variable_bed_fans: ""
variable_external_pc: ""
'''


def printer_cfg(local=''):
    return '\n'.join([
        (SUPPORT_DIR / 'printer.cfg').read_text(encoding='utf-8'),
        '[include Klipper-Chamber-Cooldown/cooldown.cfg]',
        local,
        delayed_gcode_as_macro(test_templates.ROOT / 'engine.cfg', '_COOLDOWN_LOOP', 'TEST_COOLDOWN_TICK'),
    ])


class RealKlipper(unittest.TestCase):
    def test_scripts(self):
        run_script_files(self, SCRIPTS, printer_cfg(), {
            'Klipper-Hardware-Controls': HW_ROOT,
            'Klipper-Chamber-Cooldown': test_templates.ROOT,
        })

    def test_local_tables_replace_the_shipped_ones(self):
        run_script_files(self, OVERRIDE_SCRIPTS, printer_cfg(LOCAL_OVERRIDE), {
            'Klipper-Hardware-Controls': HW_ROOT,
            'Klipper-Chamber-Cooldown': test_templates.ROOT,
        })

    def test_roles_with_several_devices_reach_every_device_that_exists(self):
        run_script_files(self, SEVERAL_SCRIPTS, printer_cfg(SEVERAL_DEVICES), {
            'Klipper-Hardware-Controls': HW_ROOT,
            'Klipper-Chamber-Cooldown': test_templates.ROOT,
        })


if __name__ == '__main__':
    unittest.main()
