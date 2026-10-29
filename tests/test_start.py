"""START_COOLDOWN: what it refuses, what it starts and what it changes."""
import unittest

from test_templates import (
    BED_FANS, CHAMBER, EXHAUST_FAN, EXTERNAL_PC, SETTINGS, VARS, CooldownTestCase, Printer, wrap)


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
            ({'arrow_band': 'x'}, 'arrow_band must be a number'),
            ({'arrow_band': -1}, 'arrow_band and idle_margin_seconds must be 0 or more'),
            ({'idle_margin_seconds': -1}, 'arrow_band and idle_margin_seconds must be 0 or more'),
            ({'status_seconds': None, 'report_minutes': 'abc'},
             'report_minutes, status_seconds must each be a number')]
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
        self.assertTrue(self.responded(printer, 'Include its hardware.cfg first'))

    def test_the_loop_ticks_every_loop_seconds_setting(self):
        printer = Printer()
        printer.state[SETTINGS].loop_seconds = 10
        printer.run('START_COOLDOWN', PROFILE='HOLD_60M_COOL_EX')
        self.assertEqual(printer.delays['_COOLDOWN_LOOP'], 10)
        self.assertEqual(printer.state[VARS].hold_loops, 360)
        printer.run('_COOLDOWN_LOOP')
        self.assertEqual(printer.delays['_COOLDOWN_LOOP'], 10)


if __name__ == '__main__':
    unittest.main()
