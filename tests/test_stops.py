"""Why the loop stops: hand changes, invalid state, print checks."""
import unittest

from test_templates import (
    BED, BED_FANS, CHAMBER, EXHAUST_FAN, SETTINGS, VARS, CooldownTestCase, Printer, wrap)


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


if __name__ == '__main__':
    unittest.main()
