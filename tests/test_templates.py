"""Cooldown behavior tests in the shared Hardware Controls simulator.

Run with: python -m unittest discover -s tests -v
Needs Klipper-Hardware-Controls checked out as hardware-controls/ beside this
README (its tests/klipper_sim.py is the simulator) and Jinja2 3.1.6.
Klipper-Configs imports this module for Printer and wrap; keep those names.
"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Appended, not prepended: Hardware Controls has test modules with the same names.
sys.path.append(str(ROOT / 'hardware-controls' / 'tests'))

import klipper_sim  # noqa: E402
from klipper_sim import State, wrap  # noqa: E402,F401  (re-exported for Klipper-Configs)

COOLDOWN_MODULES = ['profiles', 'materials', 'engine']
# What README says cooldown needs from Hardware Controls.
REQUIRED_HARDWARE_MODULES = ['hardware_names', 'fans', 'chamber']
HARDWARE_VARS = 'gcode_macro _HARDWARE_VARS'
VARS = 'gcode_macro _COOLDOWN_VARS'
SETTINGS = 'gcode_macro _COOLDOWN_SETTINGS'
PROFILES = 'gcode_macro _COOLDOWN_PROFILES'
MATERIALS = 'gcode_macro _COOLDOWN_MATERIALS'
CHAMBER = 'heater_generic chamber'
BED = 'heater_bed'
EXHAUST_FAN = 'fan_generic exhaust_fan'
EXTERNAL_PC = 'fan_generic external_pc'
BED_FANS = 'fan_generic bed_fans'
PART_FAN = 'fan'


class Printer(klipper_sim.Printer):
    """Simulated printer with Hardware Controls and, optionally, cooldown loaded."""

    def __init__(self, hardware=True, cooldown=True, tracking=False):
        super().__init__(hardware)
        if cooldown:
            for name in COOLDOWN_MODULES:
                self.load(ROOT / (name + '.cfg'))
        if tracking:
            self.load(ROOT / 'idle_timeout_tracking.cfg')

    def execute(self, line):
        # idle_timeout_tracking.cfg renames the built-in command to this one.
        if line.split()[0].upper() == 'SET_IDLE_TIMEOUT_BASE':
            self.commands.append(line)
            args = dict(token.split('=', 1) for token in line.split()[1:] if '=' in token)
            try:
                seconds = float(args['TIMEOUT'])
            except (KeyError, ValueError):
                return  # Klipper would report the bad or missing value
            if seconds > 0:
                self.idle_timeout = seconds
            return
        super().execute(line)

class CooldownTestCase(unittest.TestCase):
    """Helpers shared by the test classes below."""

    def run_until(self, printer, phase, limit=2400):
        trace = []
        for _ in range(limit):
            printer.run('_COOLDOWN_LOOP')
            cv = printer.state[VARS]
            trace.append((cv.phase, cv.phase_loops,
                          printer.state[CHAMBER].target if CHAMBER in printer.state else 0))
            if cv.phase in (0, phase):
                break
        return trace

    def custom_profile(self, printer, **changes):
        table = printer.state[PROFILES].profiles
        profile = dict(table['HOLD_60M_COOL_EX'], **changes)
        for key in [key for key, value in changes.items() if value is Ellipsis]:
            del profile[key]  # Ellipsis removes the key
        table['CUSTOM'] = wrap(profile)

    def responses(self, printer):
        return [command for command in printer.commands if command.startswith('RESPOND')]

    def responses_containing(self, printer, text):
        return [response for response in self.responses(printer) if text in response]

    def responded(self, printer, text):
        return bool(self.responses_containing(printer, text))

    def commands_containing(self, printer, text, start=0):
        return [command for command in printer.commands[start:] if text in command]

    def sent(self, printer, prefix, start=0):
        return any(command.startswith(prefix) for command in printer.commands[start:])

    def banner_numbers(self, printer):
        return [command.split('MSG="Cooldown phase ')[1][:3]
                for command in printer.commands
                if 'Cooldown phase' in command]

    def sensor_printer(self, **reading):
        """A printer whose chamber has only a temperature sensor."""
        printer = Printer()
        printer.state.pop(CHAMBER)
        printer.state['temperature_sensor enclosure'] = wrap(reading)
        printer.state[HARDWARE_VARS].chamber_heater = ''
        printer.state[HARDWARE_VARS].chamber_sensor = 'temperature_sensor enclosure'
        return printer

    def fan_minimum_printer(self, speed, **minimums):
        """Immediate-exhaust profile at `speed`.

        `minimums` maps a fan name to its fan_generic settings.
        """
        printer = Printer()
        printer.state[BED_FANS] = wrap({'speed': 0.})
        for name, fan_settings in minimums.items():
            printer.state['configfile'].settings['fan_generic ' + name] = wrap(fan_settings)
        self.custom_profile(printer, chamber_hold_minutes=0, chamber_target_temp=0,
                            cooldown_ramp_step_c=0, cooldown_ramp_step_seconds=0,
                            exhaust_fan_speed=speed)
        printer.run('START_COOLDOWN', PROFILE='CUSTOM')
        self.run_until(printer, 5)
        return printer


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


class Profiles(CooldownTestCase):
    """The profile table and what START_COOLDOWN accepts from it."""

    def test_invalid_profiles_are_refused(self):
        cases = [dict(cooldown_ramp_step_seconds=2), dict(cooldown_ramp_step_c=0),
                 dict(exhaust_fan_speed=1.5), dict(chamber_hold_minutes=-1)]
        for changes in cases:
            with self.subTest(**changes):
                printer = Printer()
                self.custom_profile(printer, **changes)
                printer.run('START_COOLDOWN', PROFILE='CUSTOM')
                self.assertEqual(printer.state[VARS].phase, 0)
                self.assertNotIn('_COOLDOWN_LOOP', printer.delays)
                self.assertTrue(any('Invalid cooldown profile CUSTOM' in command
                                    for command in printer.commands))

    def test_invalid_profile_lists_every_problem_in_one_line(self):
        # Klipper cuts a gcode line at ';', so the message must not contain one.
        printer = Printer()
        self.custom_profile(printer, chamber_hold_minutes=-1, exhaust_fan_speed=1.5)
        printer.run('START_COOLDOWN', PROFILE='CUSTOM')
        message = self.commands_containing(printer, 'Invalid cooldown profile CUSTOM')[0]
        self.assertNotIn(';', message)
        self.assertIn('Invalid cooldown profile CUSTOM: ', message)
        self.assertIn('0 or more, exhaust_fan_speed must be', message)
        self.assertTrue(message.endswith('Cooldown not started."'))

    def test_negative_ramp_target_is_refused(self):
        printer = Printer()
        self.custom_profile(printer, chamber_target_temp=-5)
        printer.run('START_COOLDOWN', PROFILE='CUSTOM')
        self.assertEqual(printer.state[VARS].phase, 0)
        self.assertNotIn('_COOLDOWN_LOOP', printer.delays)
        self.assertFalse(self.sent(printer, 'SET_IDLE_TIMEOUT'))
        message = self.responses_containing(printer, 'Invalid cooldown profile CUSTOM: ')
        self.assertEqual(len(message), 1)
        self.assertIn('chamber_target_temp must be 0 or more', message[0])

    def test_zero_ramp_target_still_means_no_ramp(self):
        printer = Printer()
        self.custom_profile(printer, chamber_target_temp=0)
        printer.run('START_COOLDOWN', PROFILE='CUSTOM')
        self.assertEqual(printer.state[VARS].phase, 1)

    def test_tiny_ramp_step_is_refused_only_when_ramping(self):
        cases = [(0.01, 42, False), (0.09, 42, False), (0.1, 42, True), (0.5, 42, True),
                 (0.01, 0, True)]
        for step, ramp_target, started in cases:
            with self.subTest(step=step, ramp_target=ramp_target):
                printer = Printer()
                self.custom_profile(printer, cooldown_ramp_step_c=step,
                                    chamber_target_temp=ramp_target)
                printer.run('START_COOLDOWN', PROFILE='CUSTOM')
                self.assertEqual(printer.state[VARS].phase, 1 if started else 0)
                refused = self.responses_containing(printer,
                                                    'cooldown_ramp_step_c must be 0.1 or more')
                self.assertEqual(len(refused), 0 if started else 1)
                if not started:
                    self.assertFalse(self.sent(printer, 'SET_IDLE_TIMEOUT'))

    def test_exhaust_enable_text_is_refused(self):
        for value in ['False', 'no', '0', 'false', None]:
            with self.subTest(value=value):
                printer = Printer()
                self.custom_profile(printer, chamber_hold_minutes=0, chamber_target_temp=0,
                                    exhaust_enable=value)
                printer.run('START_COOLDOWN', PROFILE='CUSTOM')
                self.assertEqual(printer.state[VARS].phase, 0)
                self.assertTrue(self.responded(printer, 'exhaust_enable must be True or False'))

    def test_exhaust_enable_booleans_and_zero_one_still_work(self):
        for value, speed in [(True, 1.0), (False, 0.0), (1, 1.0), (0, 0.0), (Ellipsis, 1.0)]:
            with self.subTest(value=value):
                printer = Printer()
                self.custom_profile(printer, chamber_hold_minutes=0, chamber_target_temp=0,
                                    exhaust_enable=value)
                printer.run('START_COOLDOWN', PROFILE='CUSTOM')
                self.assertEqual(printer.state[VARS].phase, 1)
                self.assertEqual(printer.state[VARS].exhaust_fan_speed, speed)

    def test_missing_or_non_numeric_profile_values_are_refused(self):
        cases = [('chamber_hold_minutes', 'abc'), ('passive_rest_minutes', None),
                 ('chamber_target_temp', 'abc'), ('cooldown_ramp_step_c', 'abc'),
                 ('cooldown_ramp_step_seconds', None), ('exhaust_fan_speed', 'abc'),
                 ('chamber_hold_minutes', Ellipsis), ('exhaust_fan_speed', Ellipsis),
                 ('chamber_hold_minutes', '60')]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                printer = Printer()
                self.custom_profile(printer, **{key: value})
                printer.run('START_COOLDOWN', PROFILE='CUSTOM')  # must not raise
                self.assertEqual(printer.state[VARS].phase, 0)
                self.assertNotIn('_COOLDOWN_LOOP', printer.delays)
                message = self.responses_containing(printer, 'Invalid cooldown profile CUSTOM')
                self.assertEqual(len(message), 1)
                self.assertIn(key, message[0])
                self.assertNotIn(';', message[0])

    def test_profile_that_is_not_a_table_is_refused(self):
        for value in ['oops', None, [1, 2]]:
            with self.subTest(value=value):
                printer = Printer()
                printer.state[PROFILES].profiles['CUSTOM'] = value
                printer.run('START_COOLDOWN', PROFILE='CUSTOM')
                self.assertEqual(printer.state[VARS].phase, 0)

    def test_fractional_minutes_are_honoured(self):
        printer = Printer()
        self.custom_profile(printer, chamber_hold_minutes=60.9, passive_rest_minutes=0.5)
        printer.run('START_COOLDOWN', PROFILE='CUSTOM')
        self.assertEqual(printer.state[VARS].hold_loops, 730)
        self.assertEqual(printer.state[VARS].passive_loops, 6)

    def test_double_quote_in_profile_name_does_not_break_the_message(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='a"b')  # raised a Malformed command before
        self.assertEqual(printer.state[VARS].phase, 0)
        self.assertTrue(self.responded(printer, "a'b"))

    def test_profile_names_with_quotes_are_refused_at_start(self):
        for name in ["O'NEIL", 'A"B']:
            with self.subTest(name=name):
                printer = Printer()
                table = printer.state[PROFILES].profiles
                table[name] = wrap(dict(table['HOLD_60M_COOL_EX']))
                printer.run('START_COOLDOWN', PROFILE=name)  # must not raise
                self.assertEqual(printer.state[VARS].phase, 0)
                self.assertNotIn('_COOLDOWN_LOOP', printer.delays)
                self.assertEqual(printer.state[VARS].cooldown_profile, 'PASSIVE_ONLY')
                self.assertFalse(self.sent(printer, 'SET_IDLE_TIMEOUT'))
                message = self.responses_containing(printer, 'cannot contain quote marks')
                self.assertEqual(len(message), 1)
                self.assertNotIn('"A"B"', message[0])

    def test_semicolon_hash_and_asterisk_in_profile_names_are_refused(self):
        for name in ['A;B', 'A#B', 'A*B']:
            with self.subTest(name=name):
                printer = Printer()
                table = printer.state[PROFILES].profiles
                table[name] = wrap(dict(table['HOLD_60M_COOL_EX']))
                printer.run('START_COOLDOWN', PROFILE=name)  # must not raise
                self.assertEqual(printer.state[VARS].phase, 0)
                self.assertNotIn('_COOLDOWN_LOOP', printer.delays)
                self.assertFalse(self.sent(printer, 'SET_IDLE_TIMEOUT'))
                refused = self.responses_containing(
                    printer, 'cannot contain quote marks, semicolons, hash signs or asterisks')
                self.assertEqual(len(refused), 1)
                self.assertNotIn(';', refused[0].split('MSG=')[1])
                printer.state[MATERIALS].materials['XX'] = name
                printer.run('COOLDOWN_SELECT', MATERIAL='XX')
                self.assertEqual(printer.state[VARS].cooldown_profile, 'PASSIVE_ONLY')
                self.assertTrue(self.responded(printer, 'asterisk in its name'))
                # the unknown-profile list echoes the bad key
                printer.run('START_COOLDOWN', PROFILE='NOPE')
                listing = self.responses_containing(printer, 'Known profiles')[0].split('MSG=')[1]
                self.assertNotIn(';', listing)
                self.assertIn('A?B', listing)

    def test_ramp_step_seconds_is_rounded_to_five_and_reported(self):
        for seconds, real in [(7, 5), (8, 10), (9, 10), (12, 10), (13, 15), (5, 5), (10, 10),
                              (120, 120)]:
            with self.subTest(seconds=seconds):
                printer = Printer()
                self.custom_profile(printer, cooldown_ramp_step_seconds=seconds)
                printer.run('START_COOLDOWN', PROFILE='CUSTOM')
                self.assertEqual(printer.state[VARS].phase, 1)
                self.assertEqual(printer.state[VARS].cooldown_ramp_step_seconds, real)
                self.assertEqual(printer.state[VARS].ramp_step_loops, real // 5)
                notes = self.responses_containing(printer, 'runs as')
                self.assertEqual(len(notes), 0 if seconds == real else 1)
                if notes:
                    self.assertIn('%d s runs as %d s' % (seconds, real), notes[0])

    def test_ramp_step_below_five_is_still_refused(self):
        for seconds in [0, 4, 4.9]:
            with self.subTest(seconds=seconds):
                printer = Printer()
                self.custom_profile(printer, cooldown_ramp_step_seconds=seconds)
                printer.run('START_COOLDOWN', PROFILE='CUSTOM')
                self.assertEqual(printer.state[VARS].phase, 0)

    def test_step_seconds_is_left_alone_when_there_is_no_ramp(self):
        printer = Printer()
        self.custom_profile(printer, chamber_target_temp=0, cooldown_ramp_step_seconds=3)
        printer.run('START_COOLDOWN', PROFILE='CUSTOM')
        self.assertEqual(printer.state[VARS].phase, 1)
        self.assertFalse(self.responded(printer, 'runs as'))


class Materials(CooldownTestCase):
    """COOLDOWN_SELECT and the material table."""

    def test_materials_select_their_mapped_profile(self):
        printer = Printer()
        cases = [('asa', 'HOLD_60M_COOL_EX'), ('PA6', 'HOLD_120M_COOL_NO_EX'),
                 ('PLA', 'IMMEDIATE_EX'), ('PCTG', 'PASSIVE_ONLY'), ('HIPS', 'PASSIVE_ONLY'),
                 ('unknown', 'PASSIVE_ONLY')]
        for material, expected in cases:
            printer.run('COOLDOWN_SELECT', MATERIAL=material)
            self.assertEqual(printer.state[VARS].cooldown_profile, expected)

    def test_unknown_material_uses_table_default(self):
        printer = Printer()
        printer.state[MATERIALS].materials['DEFAULT'] = 'IMMEDIATE_EX'
        printer.run('COOLDOWN_SELECT', MATERIAL='UNOBTAINIUM')
        self.assertEqual(printer.state[VARS].cooldown_profile, 'IMMEDIATE_EX')

    def test_unknown_material_is_reported_but_known_and_blank_are_not(self):
        printer = Printer()
        printer.run('COOLDOWN_SELECT', MATERIAL='ASAA')
        notes = self.responses_containing(printer, 'Unknown material')
        self.assertEqual(len(notes), 1)
        self.assertIn('Unknown material ASAA, using the DEFAULT profile PASSIVE_ONLY', notes[0])
        self.assertEqual(printer.state[VARS].cooldown_profile, 'PASSIVE_ONLY')
        for material in ['ASA', 'asa', ' ASA ', 'DEFAULT', '', '  ', None]:
            with self.subTest(material=material):
                printer = Printer()
                printer.run('COOLDOWN_SELECT',
                            **({} if material is None else {'MATERIAL': material}))
                self.assertFalse(self.responded(printer, 'Unknown material'))

    def test_unknown_material_with_a_quote_does_not_break_the_message(self):
        printer = Printer()
        printer.run('COOLDOWN_SELECT', MATERIAL='A"B')  # must not raise
        notes = self.responses_containing(printer, 'Unknown material')
        self.assertEqual(len(notes), 1)
        self.assertIn("Unknown material A'B,", notes[0])

    def test_cooldown_select_refuses_a_profile_that_does_not_exist(self):
        for material, mapped in [('XX', 'NOPE'), ('DEFAULT', 'NOPE'), ('YY', None)]:
            with self.subTest(material=material, mapped=mapped):
                printer = Printer()
                printer.run('COOLDOWN_SELECT', MATERIAL='ASA')
                printer.state[MATERIALS].materials[material] = mapped
                printer.run('COOLDOWN_SELECT', MATERIAL=material)  # must not raise
                # unchanged
                self.assertEqual(printer.state[VARS].cooldown_profile, 'HOLD_60M_COOL_EX')
                refused = self.responses_containing(printer, 'which is not in the profile table')
                self.assertEqual(len(refused), 1)
                self.assertIn('Profile not changed', refused[0])

    def test_cooldown_select_refuses_a_material_table_that_is_not_a_table(self):
        for broken in [['ASA', 'HOLD_60M_COOL_EX'], 'ASA', None, 5]:
            with self.subTest(table=broken):
                printer = Printer()
                printer.run('COOLDOWN_SELECT', MATERIAL='PLA')
                printer.state[MATERIALS].materials = broken
                printer.run('COOLDOWN_SELECT', MATERIAL='ASA')  # must not raise
                self.assertEqual(printer.state[VARS].cooldown_profile, 'IMMEDIATE_EX')  # unchanged
                refused = self.responses_containing(
                    printer, 'materials in _COOLDOWN_MATERIALS must be a table')
                self.assertEqual(len(refused), 1)

    def test_cooldown_select_during_a_run_leaves_the_running_profile_alone(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.run('COOLDOWN_SELECT', MATERIAL='PLA')
        self.assertEqual(printer.state[VARS].cooldown_profile, 'HOLD_60M_COOL_EX')
        self.assertEqual(len(self.responses_containing(printer, 'A cooldown is running')), 1)
        printer.run('COOLDOWN_STATUS')
        self.assertIn('Profile: HOLD_60M_COOL_EX', printer.commands[-1])
        printer.run('COOLDOWN_RESET')
        printer.run('COOLDOWN_SELECT', MATERIAL='PLA')
        self.assertEqual(printer.state[VARS].cooldown_profile, 'IMMEDIATE_EX')
        self.assertEqual(len(self.responses_containing(printer, 'A cooldown is running')), 1)

    def test_cooldown_select_accepts_a_profile_in_any_case(self):
        printer = Printer()
        printer.state[MATERIALS].materials['XX'] = 'hold_60m_cool_ex'
        printer.run('COOLDOWN_SELECT', MATERIAL='XX')
        self.assertEqual(printer.state[VARS].cooldown_profile, 'hold_60m_cool_ex')
        printer.run('START_COOLDOWN')
        self.assertEqual(printer.state[VARS].phase, 1)

    def test_material_name_is_trimmed(self):
        for material in [' ASA', 'ASA ', '  asa\t']:
            with self.subTest(material=material):
                printer = Printer()
                printer.run('COOLDOWN_SELECT', MATERIAL=material)
                self.assertEqual(printer.state[VARS].cooldown_profile, 'HOLD_60M_COOL_EX')

    def test_cooldown_select_refuses_a_profile_with_a_quote(self):
        for name in ["O'NEIL", 'A"B']:
            with self.subTest(name=name):
                printer = Printer()
                printer.state[MATERIALS].materials['XX'] = name
                printer.run('COOLDOWN_SELECT', MATERIAL='XX')  # must not raise
                self.assertEqual(printer.state[VARS].cooldown_profile, 'PASSIVE_ONLY')
                self.assertTrue(self.responded(printer, 'quote mark'))

    def test_plain_profile_names_still_work(self):
        printer = Printer()
        printer.state[MATERIALS].materials['XX'] = 'HOLD_60M_COOL_EX'
        printer.run('COOLDOWN_SELECT', MATERIAL='XX')
        self.assertEqual(printer.state[VARS].cooldown_profile, 'HOLD_60M_COOL_EX')


class Start(CooldownTestCase):
    """START_COOLDOWN refusals, fan minimums and the idle timeout it raises."""

    def test_an_explicit_profile_starts_and_an_unknown_one_is_refused(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='REST_5M_THEN_EX')
        self.assertEqual(printer.state[VARS].cooldown_profile, 'REST_5M_THEN_EX')
        self.assertEqual(printer.delays['_COOLDOWN_LOOP'], 5)
        printer.run('COOLDOWN_RESET')
        printer.run('START_COOLDOWN', PROFILE='INVALID')
        self.assertEqual(printer.state[VARS].phase, 0)
        self.assertEqual(printer.delays['_COOLDOWN_LOOP'], 0)

    def test_idle_timeout_extended_for_heated_phases_only(self):
        cases = [('HOLD_120M_COOL_NO_EX', 7200 + 13 * 120 + 600),
                 ('HOLD_60M_COOL_EX', 3600 + 13 * 120 + 600)]
        for profile, expected in cases:
            with self.subTest(profile=profile):
                printer = Printer()
                printer.run('START_COOLDOWN', PROFILE=profile)
                self.assertEqual(printer.idle_timeout, expected)
                self.run_until(printer, 3)
                self.assertEqual(printer.idle_timeout, 4800)
                self.assertEqual(printer.state[VARS].idle_timeout_extended, 0)

    def test_idle_timeout_untouched_when_not_needed(self):
        cases = [(55., 'IMMEDIATE_EX'), (55., 'REST_5M_THEN_EX'), (30., 'HOLD_120M_COOL_NO_EX')]
        for start, profile in cases:
            with self.subTest(profile=profile, start=start):
                printer = Printer()
                printer.state[CHAMBER].target = start
                printer.run('START_COOLDOWN', PROFILE=profile)
                self.run_until(printer, 5)
                printer.run('COOLDOWN_RESET')
                self.assertFalse(self.sent(printer, 'SET_IDLE_TIMEOUT'))

    def test_speed_below_a_fan_minimum_is_raised_and_reported(self):
        printer = self.fan_minimum_printer(0.05, exhaust_fan={'min_power': 0.2},
                                           external_pc={'min_power': None, 'off_below': 0.1})
        self.assertEqual(printer.state[EXHAUST_FAN].speed, 0.2)
        self.assertEqual(printer.state[EXTERNAL_PC].speed, 0.1)
        self.assertEqual(printer.state[BED_FANS].speed, 0.05)  # no minimum configured
        warnings = self.responses_containing(printer, 'below the fan minimum')
        self.assertEqual(len(warnings), 1)
        self.assertIn('exhaust_fan (0.2), external_pc (0.1)', warnings[0])
        self.assertNotIn('bed_fans', warnings[0])
        # the raised speeds are not seen as a hand change
        self.assertEqual(printer.state[VARS].phase, 5)

    def test_speed_at_or_above_the_minimum_or_zero_is_left_alone(self):
        for speed, enable in [(0.2, True), (0.5, True), (1.0, True), (0.0, True), (0.05, False)]:
            with self.subTest(speed=speed, enable=enable):
                printer = Printer()
                printer.state['configfile'].settings[EXHAUST_FAN] = wrap({'min_power': 0.2})
                self.custom_profile(printer, chamber_hold_minutes=0, chamber_target_temp=0,
                                    cooldown_ramp_step_c=0, cooldown_ramp_step_seconds=0,
                                    exhaust_fan_speed=speed, exhaust_enable=enable)
                printer.run('START_COOLDOWN', PROFILE='CUSTOM')
                self.run_until(printer, 5)
                self.assertEqual(printer.state[EXHAUST_FAN].speed, speed if enable else 0)
                self.assertFalse(self.responded(printer, 'below the fan minimum'))

    def test_start_during_a_run_is_refused_and_changes_nothing(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        for _ in range(30):
            printer.run('_COOLDOWN_LOOP')
        loops = printer.state[VARS].phase_loops
        before = len(printer.commands)
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        refused = self.commands_containing(printer, 'already running', before)
        self.assertEqual(len(refused), 1)
        self.assertIn('phase 1/5', refused[0])
        self.assertEqual(len(self.commands_containing(printer, 'Cooldown started')), 1)
        self.assertEqual(printer.state[VARS].phase, 1)
        self.assertEqual(printer.state[VARS].phase_loops, loops)  # the hold was not restarted
        self.assertEqual(printer.state[VARS].cooldown_profile, 'HOLD_60M_COOL_EX')
        self.assertFalse(self.sent(printer, ('CHAMBER', 'SET_IDLE_TIMEOUT'), before))
        printer.run('COOLDOWN_RESET')
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')  # after a reset it starts again
        self.assertEqual(printer.state[VARS].cooldown_profile, 'IMMEDIATE_EX')
        self.assertEqual(printer.state[VARS].phase, 1)

    def test_start_refuses_when_the_phase_value_is_corrupt_too(self):
        printer = Printer()
        printer.state[VARS].phase = 9  # the loop would stop on this; START must not start over it
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        self.assertEqual(len(self.commands_containing(printer, 'already running (phase 9/5)')), 1)
        self.assertEqual(len(self.commands_containing(printer, 'Cooldown started')), 0)

    def test_non_numeric_chamber_cooled_temp_is_refused_at_start(self):
        for value in ['35', None, [35]]:
            with self.subTest(value=value):
                printer = Printer()
                printer.state[SETTINGS].chamber_cooled_temp = value
                printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
                self.assertEqual(printer.state[VARS].phase, 0)
                self.assertFalse(self.sent(printer, 'SET_IDLE_TIMEOUT'))
                self.assertTrue(any(
                    'chamber_cooled_temp' in command and 'must be a number' in command
                    for command in self.responses(printer)))

    def test_a_setting_that_would_break_the_loop_is_refused_at_start(self):
        cases = [
            ({'status_seconds': 0}, 'status_seconds, stall_seconds and report_minutes times 60'),
            ({'report_minutes': 0}, 'status_seconds, stall_seconds and report_minutes times 60'),
            ({'stall_seconds': 1}, 'status_seconds, stall_seconds and report_minutes times 60'),
            ({'loop_seconds': 0}, 'loop_seconds must be a whole number of 1 or more'),
            ({'loop_seconds': -5}, 'loop_seconds must be a whole number of 1 or more'),
            ({'loop_seconds': 2.5}, 'loop_seconds must be a whole number of 1 or more'),
            ({'arrow_band': 'x'}, 'arrow_band must be numbers'),
            ({'arrow_band': -1}, 'arrow_band and idle_margin_seconds must be 0 or more'),
            ({'idle_margin_seconds': -1}, 'arrow_band and idle_margin_seconds must be 0 or more'),
            ({'status_seconds': None, 'report_minutes': 'abc'},
             'report_minutes, status_seconds must be numbers')]
        for changes, expected in cases:
            with self.subTest(**changes):
                printer = Printer()
                for key, value in changes.items():
                    setattr(printer.state[SETTINGS], key, value)
                printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
                self.assertEqual(printer.state[VARS].phase, 0)
                self.assertNotIn('_COOLDOWN_LOOP', printer.delays)
                self.assertFalse(self.sent(printer, 'SET_IDLE_TIMEOUT'))
                self.assertFalse(self.sent(printer, 'SET_HEATER_TEMPERATURE'))
                message = self.responses_containing(printer, 'Invalid _COOLDOWN_SETTINGS: ')
                self.assertEqual(len(message), 1)
                self.assertIn(expected, message[0])
                self.assertTrue(message[0].endswith('Cooldown not started."'))

    def test_the_settings_it_ships_with_start_a_cooldown(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        self.assertEqual(printer.state[VARS].phase, 1)

    def test_profile_name_in_any_case_and_known_profiles_listed(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='immediate_ex')
        self.assertEqual(printer.state[VARS].cooldown_profile, 'IMMEDIATE_EX')
        self.assertEqual(printer.state[VARS].phase, 1)
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='NOPE')
        message = self.responses_containing(printer, 'Unknown cooldown profile')
        self.assertEqual(len(message), 1)
        self.assertIn('Known profiles: HOLD_120M_COOL_NO_EX, HOLD_30M_COOL_EX', message[0])
        self.assertNotIn(';', message[0])


    def test_start_without_hardware_controls_says_to_install_it(self):
        printer = Printer(hardware=False)
        printer.state['configfile'] = wrap({'settings': {}})
        printer.state['heater_generic chamber'] = wrap({'target': 55., 'temperature': 55.})
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        self.assertEqual(printer.state[VARS].phase, 0)
        self.assertTrue(self.responded(printer, 'Klipper-Hardware-Controls is not installed'))

    def test_the_loop_ticks_every_loop_seconds_setting(self):
        printer = Printer()
        printer.state[SETTINGS].loop_seconds = 10
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        self.assertEqual(printer.delays['_COOLDOWN_LOOP'], 10)
        self.assertEqual(printer.state[VARS].hold_loops, 360)
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.delays['_COOLDOWN_LOOP'], 10)


class StatusAndReport(CooldownTestCase):
    """COOLDOWN_STATUS and the progress lines the loop prints."""

    def test_chamber_arrow_is_level_when_the_reading_is_at_the_target(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.run('_COOLDOWN_LOOP')
        report = [command
                  for command in printer.commands
                  if command.startswith('RESPOND PREFIX="📃"')]
        self.assertTrue(report)
        self.assertIn('Chamber →', report[0])

    def test_bed_arrow_compares_with_displayed_target(self):
        printer = Printer()
        printer.state[BED].temperature = 34.
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.run('_COOLDOWN_LOOP')
        report = [command
                  for command in printer.commands
                  if command.startswith('RESPOND PREFIX="📃"')]
        self.assertIn('Bed → 034.0/035.0', report[0])

    def test_status_names_the_phase(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.run('COOLDOWN_STATUS')
        self.assertIn('Phase: 1 HOLD', printer.commands[-1])
        printer.run('COOLDOWN_RESET')
        printer.run('COOLDOWN_STATUS')
        self.assertIn('Phase: 0 IDLE', printer.commands[-1])

    def test_status_warns_when_the_loop_has_not_run_for_a_minute(self):
        printer = Printer()
        printer.state['toolhead'] = wrap({'estimated_print_time': 100.})
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        self.assertEqual(printer.state[VARS].last_tick, 100.)
        printer.state['toolhead'].estimated_print_time = 130.
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].last_tick, 130.)
        printer.state['toolhead'].estimated_print_time = 190.
        printer.run('COOLDOWN_STATUS')
        self.assertFalse(any('cooldown loop last ran' in command for command in printer.commands))
        printer.state['toolhead'].estimated_print_time = 400.  # the loop was stopped by hand
        printer.run('COOLDOWN_STATUS')
        warnings = self.responses_containing(printer, 'cooldown loop last ran 270 s ago')
        self.assertEqual(len(warnings), 1)
        self.assertIn('Run COOLDOWN_RESET', warnings[0])
        printer.run('_COOLDOWN_LOOP')
        printer.run('COOLDOWN_STATUS')
        self.assertEqual(len(self.commands_containing(printer, 'cooldown loop last ran')), 1)
        printer.run('COOLDOWN_RESET')
        self.assertEqual(printer.state[VARS].last_tick, 0)
        printer.state['toolhead'].estimated_print_time = 900.
        printer.run('COOLDOWN_STATUS')
        self.assertEqual(len(self.commands_containing(printer, 'cooldown loop last ran')), 1)

    def test_status_without_a_toolhead_object_does_not_warn(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.run('_COOLDOWN_LOOP')
        printer.run('COOLDOWN_STATUS')  # no 'toolhead' in printer: must not raise
        self.assertEqual(printer.state[VARS].last_tick, 0)
        self.assertFalse(any('cooldown loop last ran' in command for command in printer.commands))

    def test_a_toolhead_without_a_clock_does_not_raise(self):
        printer = Printer()
        # Klipper-Configs' simulated toolhead has no clock
        printer.state['toolhead'] = wrap({'homed_axes': 'xyz'})
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.run('_COOLDOWN_LOOP')
        printer.run('COOLDOWN_STATUS')
        self.assertEqual(printer.state[VARS].phase, 1)
        self.assertEqual(printer.state[VARS].last_tick, 0)

    def test_status_shows_a_question_mark_outside_the_phase_range(self):
        for phase in [-1, -6, 6, 9]:
            with self.subTest(phase=phase):
                printer = Printer()
                printer.state[VARS].phase = phase
                printer.run('COOLDOWN_STATUS')
                self.assertIn('Phase: %d ?' % phase, printer.commands[-1])

    def test_ramp_progress_line_is_rounded(self):
        printer = Printer()
        printer.state[CHAMBER].target = 45.3
        self.custom_profile(printer, chamber_hold_minutes=0, cooldown_ramp_step_c=0.1,
                            cooldown_ramp_step_seconds=5)
        printer.run('START_COOLDOWN', PROFILE='CUSTOM')
        self.run_until(printer, 3)
        progress = self.commands_containing(printer, 'Cooldown RAMP: chamber target')
        self.assertTrue(progress)
        for line in progress:
            self.assertRegex(line, r'chamber target \d+\.\d°C')


class Reset(CooldownTestCase):
    """COOLDOWN_RESET."""

    def test_reset_restores_extended_idle_timeout_once(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='HOLD_120M_COOL_NO_EX')
        printer.run('COOLDOWN_RESET')
        self.assertEqual(printer.idle_timeout, 4800)
        printer.idle_timeout = 43200.
        printer.run('COOLDOWN_RESET')
        self.assertEqual(printer.idle_timeout, 43200)

    def test_reset_leaves_heaters_and_fans(self):
        printer = Printer()
        printer.state[EXHAUST_FAN].speed = .5
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.run('COOLDOWN_RESET')
        self.assertEqual(printer.state[CHAMBER].target, 55)
        self.assertEqual(printer.state[EXHAUST_FAN].speed, .5)
        self.assertEqual(printer.state[VARS].cooldown_ramp_step_seconds, 0)

    def test_reset_reports_a_running_cooldown_only(self):
        printer = Printer()
        printer.run('COOLDOWN_RESET')
        self.assertFalse(any('Cooldown reset' in command for command in printer.commands))
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.run('COOLDOWN_RESET')
        self.assertEqual(len(self.commands_containing(printer, 'Cooldown reset')), 1)


class Phases(CooldownTestCase):
    """Phase transitions, banners, rest, exhaust and completion."""

    def test_all_profiles_reach_final_phase(self):
        for profile in Printer().state[PROFILES].profiles:
            with self.subTest(profile=profile):
                printer = Printer()
                printer.run('START_COOLDOWN', PROFILE=profile)
                for _ in range(2400):
                    printer.run('_COOLDOWN_LOOP')
                    if printer.state[VARS].phase == 5:
                        break
                self.assertEqual(printer.state[VARS].phase, 5)
                printer.state[CHAMBER].temperature = 34.
                printer.state[BED].temperature = 34.
                printer.run('_COOLDOWN_LOOP')
                self.assertEqual(printer.state[VARS].phase, 0)
                self.assertEqual(printer.delays['_COOLDOWN_LOOP'], 0)

    def test_heater_released_for_every_profile_and_start_target(self):
        for start in [55., 30., 0.]:
            for profile in Printer().state[PROFILES].profiles:
                with self.subTest(profile=profile, start=start):
                    printer = Printer()
                    printer.state[CHAMBER].target = start
                    printer.run('START_COOLDOWN', PROFILE=profile)
                    trace = self.run_until(printer, 5)
                    self.assertEqual(trace[-1][0], 5)
                    self.assertTrue(all(target == 0 for phase, _, target in trace if phase >= 3))

    def test_one_transition_per_tick(self):
        profiles = Printer().state[PROFILES].profiles
        for profile, start in [(profile, start) for profile in profiles for start in [55., 30.]]:
            with self.subTest(profile=profile, start=start):
                printer = Printer()
                printer.state[CHAMBER].target = start
                printer.run('START_COOLDOWN', PROFILE=profile)
                previous = (1, 0)
                for phase, loops, _ in self.run_until(printer, 5):
                    if phase == previous[0]:
                        self.assertEqual(loops, previous[1] + 1)
                    else:
                        self.assertGreater(phase, previous[0])
                        self.assertEqual(loops, 0)
                    previous = (phase, loops)

    def test_completion_turns_heater_and_fans_off(self):
        printer = Printer()
        printer.state[CHAMBER].update(target=30., temperature=30.)
        printer.state[BED].temperature = 30.
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 0)
        self.assertEqual(printer.state[CHAMBER].target, 0)
        self.assertIn('RESET_FANS', printer.commands)

    def test_completion_turns_every_heater_and_fan_off(self):
        for bed_heater in [BED, 'heater_generic buildplate']:
            with self.subTest(bed_heater=bed_heater):
                printer = Printer()
                if bed_heater != BED:
                    printer.state[bed_heater] = printer.state.pop(BED)
                    printer.state[HARDWARE_VARS].bed_heater = bed_heater
                printer.state[CHAMBER].update(target=30., temperature=30.)
                printer.state[bed_heater].update(target=30., temperature=30.)
                printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
                # part fan and external_pc are not tracked, so they are not a hand change
                printer.state[PART_FAN].speed = 0.7
                printer.state[EXTERNAL_PC].speed = 0.6
                printer.run('_COOLDOWN_LOOP')
                self.assertEqual(printer.state[VARS].phase, 0)
                self.assertEqual(printer.state[CHAMBER].target, 0)
                self.assertEqual(printer.state[bed_heater].target, 0)
                self.assertEqual(printer.state[PART_FAN].speed, 0)
                self.assertEqual(printer.state[EXTERNAL_PC].speed, 0)
                self.assertEqual(printer.state[EXHAUST_FAN].speed, 0)

    def test_completion_leaves_a_bed_that_is_already_off_alone(self):
        printer = Printer()
        printer.state[CHAMBER].update(target=30., temperature=30.)
        printer.state[BED].update(target=0., temperature=30.)
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 0)
        self.assertFalse(self.sent(printer, 'SET_HEATER_TEMPERATURE HEATER=heater_bed'))

    def test_passive_rest_turns_exhaust_off(self):
        printer = Printer()
        printer.state[EXHAUST_FAN].speed = 1.
        printer.run('START_COOLDOWN', PROFILE='REST_5M_THEN_EX')
        self.run_until(printer, 3)
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 3)
        self.assertEqual(printer.state[EXHAUST_FAN].speed, 0)
        self.run_until(printer, 5)
        self.assertEqual(printer.state[EXHAUST_FAN].speed, 1)

    def test_rest_turns_external_pc_and_bed_fans_off_too(self):
        printer = Printer()
        printer.state[BED_FANS] = wrap({'speed': 0.6})
        printer.state[EXTERNAL_PC].speed = 0.6
        printer.state[EXHAUST_FAN].speed = 0.6
        printer.run('START_COOLDOWN', PROFILE='REST_5M_THEN_EX')
        self.run_until(printer, 3)
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 3)
        for fan in ['exhaust_fan', 'external_pc', 'bed_fans']:
            self.assertEqual(printer.state['fan_generic ' + fan].speed, 0, fan)
        for _ in range(10):  # the rest keeps running: its own fan changes are not a hand change
            printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 3)
        self.run_until(printer, 5)
        for fan in ['exhaust_fan', 'external_pc', 'bed_fans']:
            self.assertEqual(printer.state['fan_generic ' + fan].speed, 1, fan)

    def test_rest_turns_a_hot_bed_off_and_says_so(self):
        # rest and no-rest paths both release the bed
        for profile in ['REST_5M_THEN_EX', 'HOLD_60M_COOL_EX']:
            with self.subTest(profile=profile):
                printer = Printer()
                printer.state[BED].update(target=100., temperature=95.)
                printer.run('START_COOLDOWN', PROFILE=profile)
                # held until the passive phases begin
                self.assertEqual(printer.state[BED].target, 100)
                self.run_until(printer, 3)
                printer.run('_COOLDOWN_LOOP')
                # a profile without a rest moves on at once
                self.assertIn(printer.state[VARS].phase, (3, 4))
                self.assertEqual(printer.state[BED].target, 0)
                notes = self.responses_containing(printer, 'Bed heater turned off')
                self.assertEqual(len(notes), 1)
                self.assertIn('target was 100', notes[0])
                for _ in range(3):  # its own change is not mistaken for a hand change
                    printer.run('_COOLDOWN_LOOP')
                self.assertNotEqual(printer.state[VARS].phase, 0)
                self.assertFalse(self.responded(printer, 'changed by hand'))

    def test_rest_leaves_a_bed_that_is_already_off_alone(self):
        printer = Printer()
        printer.state[BED].update(target=0., temperature=60.)
        printer.run('START_COOLDOWN', PROFILE='REST_5M_THEN_EX')
        self.run_until(printer, 3)
        printer.run('_COOLDOWN_LOOP')
        self.assertFalse(self.sent(printer, 'SET_HEATER_TEMPERATURE HEATER=heater_bed'))
        self.assertFalse(self.responded(printer, 'Bed heater turned off'))

    def test_fans_are_left_alone_when_there_is_no_rest(self):
        printer = Printer()
        printer.state[EXTERNAL_PC].speed = 0.6
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        self.run_until(printer, 3)
        self.assertEqual(printer.state[VARS].phase, 3)
        self.assertEqual(printer.state[EXTERNAL_PC].speed, 0.6)

    def test_exhaust_enable_is_honored(self):
        printer = Printer()
        self.custom_profile(printer, chamber_hold_minutes=0, chamber_target_temp=0,
                            exhaust_enable=False, exhaust_fan_speed=1.0)
        printer.run('START_COOLDOWN', PROFILE='CUSTOM')
        self.assertEqual(self.run_until(printer, 5)[-1][0], 5)
        self.assertEqual(printer.state[EXHAUST_FAN].speed, 0)

    def test_exhaust_banner_names_each_fan_when_the_speeds_differ(self):
        printer = self.fan_minimum_printer(0.05, exhaust_fan={'min_power': 0.2},
                                           external_pc={'min_power': None, 'off_below': 0.1})
        banners = self.responses_containing(printer, 'phase 4/5')
        self.assertEqual(len(banners), 1)
        self.assertIn('EXHAUST: exhaust_fan to 0.2, external_pc to 0.1, bed_fans to 0.05',
                      banners[0])

    def test_exhaust_banner_keeps_one_speed_when_the_fans_agree(self):
        for speed, minimums in [(0.5, {}), (0.5, {'exhaust_fan': {'min_power': 0.2}}), (0.0, {})]:
            with self.subTest(speed=speed):
                printer = self.fan_minimum_printer(speed, **minimums)
                banners = self.responses_containing(printer, 'phase 4/5')
                self.assertEqual(len(banners), 1)
                self.assertIn('EXHAUST: fans to %s"' % speed, banners[0])

    def test_ramp_step_does_not_overshoot(self):
        printer = Printer()
        printer.state[CHAMBER].target = 44.
        self.custom_profile(printer, chamber_hold_minutes=0, cooldown_ramp_step_c=5)
        printer.run('START_COOLDOWN', PROFILE='CUSTOM')
        targets = [target for phase, _, target in self.run_until(printer, 3) if phase == 2]
        self.assertEqual(sorted(set(targets)), [42., 44.])

    def test_unused_phases_are_shown_as_skipped(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        self.run_until(printer, 5)
        banners = self.commands_containing(printer, 'Cooldown phase')
        self.assertEqual([b.split('MSG="Cooldown phase ')[1][:3] for b in banners],
                         ['1/5', '2/5', '3/5', '4/5', '5/5'])
        self.assertIn('HOLD: skipped, profile has no hold', banners[0])
        self.assertIn('RAMP: skipped, profile has no ramp', banners[1])
        self.assertIn('rest skipped, profile has no rest', banners[2])
        for line in ['Hold complete', 'Rest complete', 'skipping ramp', '0.0°C every 0 s']:
            self.assertFalse(any(line in command for command in printer.commands), line)

    def test_skipped_hold_and_ramp_still_count_to_five(self):
        printer = Printer()
        printer.state[CHAMBER].target = 30.
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        self.run_until(printer, 5)
        self.assertEqual(self.banner_numbers(printer), ['1/5', '2/5', '3/5', '4/5', '5/5'])
        self.assertTrue(any('RAMP: skipped' in command for command in printer.commands))


class Stops(CooldownTestCase):
    """Everything that stops a running cooldown, and how it says so."""

    def test_changing_the_chamber_target_by_hand_stops_the_cooldown(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.state[CHAMBER].target = 50.
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 0)

    def test_loop_stops_cleanly_on_invalid_state(self):
        cases = [(SETTINGS, 'chamber_cooled_temp', None), (SETTINGS, 'chamber_cooled_temp', '35'),
                 (VARS, 'hold_loops', 'abc'), (VARS, 'ramp_step_loops', 'abc'),
                 (VARS, 'cooldown_ramp_step_c', 'abc'), (VARS, 'cooldown_ramp_step_seconds', 'abc'),
                 (VARS, 'exhaust_fan_speed', 'abc'), (VARS, 'ramp_chamber_target_temp', '42'),
                 (VARS, 'phase', 7), (VARS, 'phase', -1), (VARS, 'phase', 'abc')]
        for macro, var, value in cases:
            with self.subTest(var=var, value=value):
                printer = Printer()
                printer.state[CHAMBER].target = 62.
                printer.state[BED].target = 100.
                printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
                printer.state[macro][var] = value
                printer.run('_COOLDOWN_LOOP')  # must not raise
                self.assertEqual(printer.state[VARS].phase, 0)
                self.assertEqual(printer.state[CHAMBER].target, 0)
                self.assertEqual(printer.state[BED].target, 0)
                self.assertEqual(printer.delays['_COOLDOWN_LOOP'], 0)
                self.assertEqual(printer.idle_timeout, 4800)
                self.assertTrue(self.responded(printer, 'not valid'))

    def test_loop_stops_cleanly_when_a_reading_disappears(self):
        printer = self.sensor_printer(temperature=50.)
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        self.assertEqual(printer.state[VARS].phase, 1)
        printer.state['temperature_sensor enclosure'] = wrap({})
        printer.run('_COOLDOWN_LOOP')  # must not raise
        self.assertEqual(printer.state[VARS].phase, 0)
        self.assertEqual(printer.delays['_COOLDOWN_LOOP'], 0)
        self.assertTrue(self.responded(printer, 'cannot be read'))
        self.assertTrue(self.responded(printer, 'The heaters are off'))

    def test_loop_stops_cleanly_when_the_chamber_reading_disappears_and_turns_the_heaters_off(
            self):
        printer = Printer()
        printer.state[CHAMBER].target = 62.
        printer.state[BED].target = 100.
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.state[CHAMBER].temperature = None
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 0)
        self.assertEqual(printer.state[CHAMBER].target, 0)
        self.assertEqual(printer.state[BED].target, 0)

    def test_print_check_uses_print_stats_not_idle_timeout(self):
        printer = Printer()
        printer.state['print_stats'] = wrap({'state': 'standby'})
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        self.run_until(printer, 5)
        for _ in range(8):
            printer.state['idle_timeout'].state = 'Printing'  # G4, homing, QGL, LOAD_FILAMENT ...
            printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 5)
        printer.state['print_stats'].state = 'printing'
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.state[VARS].phase, 0)
        self.assertTrue(self.responded(printer, 'started printing'))

    def test_print_check_without_print_stats_object(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='IMMEDIATE_EX')
        self.run_until(printer, 5)
        printer.run('_COOLDOWN_LOOP')  # no 'print_stats' in printer: must not raise
        self.assertEqual(printer.state[VARS].phase, 5)

    def test_engine_stops_do_not_add_a_reset_line(self):
        def changed_by_hand(printer):
            printer.state[CHAMBER].target = 50.

        def invalid_value(printer):
            printer.state[VARS].hold_loops = 'abc'

        def unreadable_sensor(printer):
            printer.state[CHAMBER].pop('temperature')

        def printing(printer):
            printer.state['print_stats'] = wrap({'state': 'printing'})

        for stop, change in [('changed by hand', changed_by_hand), ('not valid', invalid_value),
                             ('cannot be read', unreadable_sensor), ('started printing', printing)]:
            with self.subTest(stop=stop):
                printer = Printer()
                printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
                change(printer)
                printer.run('_COOLDOWN_LOOP')
                self.assertEqual(printer.state[VARS].phase, 0)
                self.assertTrue(any(stop in command for command in printer.commands))
                self.assertFalse(any('Cooldown reset' in command for command in printer.commands))

    def test_hand_change_stop_names_what_changed_and_leaves_it_alone(self):
        def chamber(printer):
            printer.state[CHAMBER].target = 0.

        def bed(printer):
            printer.state[BED].target = 60.

        def exhaust(printer):
            printer.state[EXHAUST_FAN].speed = 0.5

        def bed_fans(printer):
            printer.state[BED_FANS].speed = 0.5

        changes = [('chamber target', chamber), ('bed target', bed),
                   ('exhaust fan speed', exhaust), ('bed fans speed', bed_fans)]
        for name, change in changes:
            for profile in ['HOLD_60M_COOL_EX', 'IMMEDIATE_EX']:
                with self.subTest(changed=name, profile=profile):
                    printer = Printer()
                    printer.state[BED_FANS] = wrap({'speed': 0.})
                    printer.run('START_COOLDOWN', PROFILE=profile)
                    if profile == 'HOLD_60M_COOL_EX':
                        # still in HOLD, a RAMP would have followed
                        self.run_until(printer, 2, limit=1)
                    change(printer)
                    before = len(printer.commands)
                    printer.run('_COOLDOWN_LOOP')
                    self.assertEqual(printer.state[VARS].phase, 0)
                    self.assertEqual(printer.delays['_COOLDOWN_LOOP'], 0)  # the loop is cancelled
                    stop = self.commands_containing(printer, 'changed by hand', before)
                    self.assertEqual(len(stop), 1)
                    self.assertIn('hand (%s).' % name, stop[0])
                    self.assertIn('cancelled', stop[0])
                    self.assertNotIn(';', stop[0].split('MSG=')[1])
                    self.assertFalse(self.sent(
                        printer, ('CHAMBER', 'EXHAUST_FAN', 'BED_FANS', 'RESET_FANS'), before))

    def test_hand_change_stop_lists_every_change(self):
        printer = Printer()
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.state[CHAMBER].target = 0.
        printer.state[BED].target = 60.
        printer.run('_COOLDOWN_LOOP')
        stop = self.commands_containing(printer, 'changed by hand')[0]
        self.assertIn('(chamber target, bed target)', stop)

    def test_completion_does_not_add_a_reset_line(self):
        printer = Printer()
        printer.state[CHAMBER].update(target=30., temperature=30.)
        printer.state[BED].temperature = 30.
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        printer.run('_COOLDOWN_LOOP')
        self.assertTrue(any('Cooldown complete' in command for command in printer.commands))
        self.assertFalse(any('Cooldown reset' in command for command in printer.commands))


class IdleTimeoutTracking(CooldownTestCase):
    """idle_timeout_tracking.cfg and the timeout the cooldown hands back."""

    def test_a_timeout_set_by_hand_is_remembered(self):
        printer = Printer(tracking=True)
        printer.run('SET_IDLE_TIMEOUT', TIMEOUT=2000)
        self.assertEqual(printer.idle_timeout, 2000)
        self.assertEqual(printer.state[VARS].user_idle_timeout, 2000)

    def test_cooldown_extends_from_the_timeout_in_force_and_hands_it_back(self):
        for hand, expected_start in [(2000, 9360), (4800, 9360)]:
            with self.subTest(hand=hand):
                printer = Printer(tracking=True)
                printer.run('SET_IDLE_TIMEOUT', TIMEOUT=hand)
                printer.run('START_COOLDOWN', PROFILE='HOLD_120M_COOL_NO_EX')
                self.assertEqual(printer.idle_timeout, expected_start)
                # its own change is not recorded
                self.assertEqual(printer.state[VARS].user_idle_timeout, hand)
                self.run_until(printer, 3)
                self.assertEqual(printer.idle_timeout, hand)
                self.assertEqual(printer.state[VARS].idle_timeout_extended, 0)

    def test_a_longer_timeout_set_by_hand_is_not_shortened_or_replaced(self):
        for profile in ['HOLD_120M_COOL_NO_EX', 'REST_5M_THEN_EX']:
            with self.subTest(profile=profile):
                printer = Printer(tracking=True)
                printer.run('SET_IDLE_TIMEOUT', TIMEOUT=999999)  # DISABLE_TIMEOUT
                printer.run('START_COOLDOWN', PROFILE=profile)
                self.assertEqual(printer.idle_timeout, 999999)
                self.assertEqual(printer.state[VARS].idle_timeout_extended, 0)
                self.run_until(printer, 4)
                printer.run('COOLDOWN_RESET')
                self.assertEqual(printer.idle_timeout, 999999)

    def test_a_shorter_timeout_set_during_the_cooldown_waits_until_the_heater_is_released(self):
        printer = Printer(tracking=True)
        printer.run('START_COOLDOWN', PROFILE='HOLD_120M_COOL_NO_EX')
        self.assertEqual(printer.idle_timeout, 9360)
        printer.run('SET_IDLE_TIMEOUT', TIMEOUT=1000)  # a RESUME putting the configured value back
        self.assertEqual(printer.idle_timeout, 9360)
        self.assertEqual(printer.state[VARS].user_idle_timeout, 1000)
        self.assertTrue(self.responded(
            printer, 'Idle timeout kept at 9360 s while the cooldown runs, then set to 1000 s'))
        self.run_until(printer, 3)
        self.assertEqual(printer.idle_timeout, 1000)

    def test_a_longer_timeout_set_during_the_cooldown_is_applied_and_handed_back(self):
        printer = Printer(tracking=True)
        printer.run('START_COOLDOWN', PROFILE='HOLD_120M_COOL_NO_EX')
        printer.run('SET_IDLE_TIMEOUT', TIMEOUT=43200)  # PAUSE
        self.assertEqual(printer.idle_timeout, 43200)
        self.assertFalse(self.responded(printer, 'Idle timeout kept'))
        self.run_until(printer, 3)
        self.assertEqual(printer.idle_timeout, 43200)

    def test_reset_hands_back_the_timeout_set_by_hand(self):
        printer = Printer(tracking=True)
        printer.run('SET_IDLE_TIMEOUT', TIMEOUT=2000)
        printer.run('START_COOLDOWN', PROFILE='HOLD_120M_COOL_NO_EX')
        printer.run('COOLDOWN_RESET')
        self.assertEqual(printer.idle_timeout, 2000)
        # reset keeps what was set by hand
        self.assertEqual(printer.state[VARS].user_idle_timeout, 2000)
        self.assertEqual(printer.state[VARS].extended_idle_timeout, 0)

    def test_without_a_hand_set_timeout_the_configured_one_comes_back(self):
        printer = Printer(tracking=True)
        printer.run('START_COOLDOWN', PROFILE='HOLD_120M_COOL_NO_EX')
        self.assertEqual(printer.idle_timeout, 9360)
        self.assertEqual(printer.state[VARS].user_idle_timeout, 0)
        self.run_until(printer, 3)
        self.assertEqual(printer.idle_timeout, 4800)

    def test_timeout_values_klipper_should_judge_are_passed_on_unrecorded(self):
        for params in [{'TIMEOUT': 'abc'}, {'TIMEOUT': 0}, {'TIMEOUT': -5}, {'TIMEOUT': 'inf'}, {}]:
            with self.subTest(params=params):
                printer = Printer(tracking=True)
                printer.run('SET_IDLE_TIMEOUT', **params)
                self.assertEqual(printer.state[VARS].user_idle_timeout, 0)
                self.assertTrue(self.sent(printer, 'SET_IDLE_TIMEOUT_BASE'))


if __name__ == '__main__':
    unittest.main()
