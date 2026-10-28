"""Profile validation, ramps and profile names."""
import unittest

from test_templates import (
    MATERIALS, PROFILES, VARS, CooldownTestCase, Printer, wrap)


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


if __name__ == '__main__':
    unittest.main()
