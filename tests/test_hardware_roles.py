"""Which devices cooldown needs: sensor-only chamber, other names, missing fans and sensors."""
import unittest

from test_templates import (
    BED, BED_FANS, CHAMBER, COOLDOWN_MODULES, EXHAUST_FAN, EXTERNAL_PC, HARDWARE_VARS,
    REQUIRED_HARDWARE_MODULES, ROOT, SETTINGS, VARS, CooldownTestCase, Printer, wrap)
import klipper_sim


class HardwareRoles(CooldownTestCase):
    """Which devices exist: sensor-only chamber, other names, missing fans and sensors."""

    def test_runs_with_only_required_hardware_modules(self):
        printer = Printer(hardware=False, cooldown=False)
        for name in REQUIRED_HARDWARE_MODULES:
            printer.load(klipper_sim.module_path(name))
        printer.load(klipper_sim.HARDWARE_LOCAL)
        for name in COOLDOWN_MODULES:
            printer.load(ROOT / (name + '.cfg'))
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        for _ in range(5):
            printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 5)
        self.assertEqual(printer.state[EXHAUST_FAN].speed, 1)

    def test_sensor_only_chamber(self):
        printer = Printer()
        printer.state.pop(CHAMBER)
        printer.state['temperature_sensor enclosure'] = wrap({'temperature': 50.})
        printer.state[HARDWARE_VARS].chamber_heater = ''
        printer.state[HARDWARE_VARS].chamber_sensor = 'temperature_sensor enclosure'
        printer.run('START_COOLDOWN', PROFILE='PASSIVE_ONLY')
        for _ in range(8):
            printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 5)

    def test_alternate_hardware_names(self):
        printer = Printer()
        hw = printer.state[HARDWARE_VARS]
        renames = [('chamber_heater', CHAMBER, 'heater_generic enclosure'),
                   ('bed_heater', BED, 'heater_generic buildplate'),
                   ('exhaust_fan', EXHAUST_FAN, 'fan_generic vent')]
        for role, old, new in renames:
            printer.state[new] = printer.state.pop(old)
            hw[role] = new.split(' ', 1)[-1] if role != 'bed_heater' else new
        hw.chamber_sensor = 'heater_generic enclosure'
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        for _ in range(12):
            printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state['fan_generic vent'].speed, 1)

    def test_no_heater_still_counts_to_five(self):
        printer = self.sensor_printer(temperature=50.)
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        self.run_until(printer, 5)
        self.assertEqual(self.banner_numbers(printer), ['1/5', '2/5', '3/5', '4/5', '5/5'])

    def test_bed_fans_only_printer_gets_its_fans(self):
        printer = Printer()
        printer.state.pop(EXHAUST_FAN)
        printer.state.pop(EXTERNAL_PC)
        printer.state[BED_FANS] = wrap({'speed': 0.})
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        self.run_until(printer, 5)
        self.assertEqual(printer.state[BED_FANS].speed, 1)
        self.assertFalse(any('skipping exhaust' in command for command in printer.commands))

    def test_no_fans_at_all_still_skips_with_a_message(self):
        printer = Printer()
        printer.state.pop(EXHAUST_FAN)
        printer.state.pop(EXTERNAL_PC)
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        self.run_until(printer, 5)
        self.assertTrue(any('skipping exhaust' in command for command in printer.commands))

    def test_sensor_only_chamber_threshold_change_is_not_an_override(self):
        printer = self.sensor_printer(temperature=50.)
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        self.run_until(printer, 5)
        printer.state[SETTINGS].chamber_cooled_temp = 30
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 5)
        self.assertFalse(any('changed by hand' in command for command in printer.commands))

    def test_sensor_without_temperature_is_refused_at_start(self):
        printer = self.sensor_printer()  # an object with no temperature key
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        self.assertEqual(printer.state[VARS].phase, 0)
        self.assertNotIn('_COOLDOWN_LOOP', printer.delays)
        self.assertTrue(any('chamber_sensor' in command and 'has no temperature' in command
                            for command in self.responses(printer)))

    def test_bed_heater_without_temperature_is_refused_at_start(self):
        printer = Printer()
        printer.state[BED].pop('temperature')
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        self.assertEqual(printer.state[VARS].phase, 0)
        self.assertTrue(any('bed_heater' in command and 'has no temperature' in command
                            for command in self.responses(printer)))

    def test_a_working_sensor_still_starts(self):
        printer = self.sensor_printer(temperature=50.)
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        self.assertEqual(printer.state[VARS].phase, 1)

    def test_no_chamber_device_warns_and_waits_for_the_bed(self):
        printer = Printer()
        printer.state.pop(CHAMBER)
        printer.state[HARDWARE_VARS].chamber_heater = ''
        printer.state[BED].temperature = 80.
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        self.assertEqual(printer.state[VARS].phase, 1)
        self.assertTrue(self.responded(printer, 'No chamber heater or chamber sensor found'))
        self.run_until(printer, 5)
        self.assertEqual(self.banner_numbers(printer), ['1/5', '2/5', '3/5', '4/5', '5/5'])
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 5)
        printer.state[BED].temperature = 30.
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 0)

    def test_a_sensor_name_with_no_object_counts_as_no_chamber_device(self):
        printer = Printer()
        printer.state.pop(CHAMBER)
        printer.state[HARDWARE_VARS].chamber_heater = ''
        printer.state[HARDWARE_VARS].chamber_sensor = 'temperature_sensor missing'
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        self.assertTrue(self.responded(printer, 'No chamber heater or chamber sensor found'))

    def test_a_heater_or_a_sensor_does_not_warn_about_the_chamber(self):
        for printer in (Printer(), self.sensor_printer(temperature=50.)):
            printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
            self.assertEqual(printer.state[VARS].phase, 1)
            self.assertFalse(self.responded(printer, 'No chamber heater or chamber sensor'))


if __name__ == '__main__':
    unittest.main()
