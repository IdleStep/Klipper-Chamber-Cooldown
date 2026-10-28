"""The status line, the arrows and the progress report."""
import unittest

from test_templates import (
    BED, CHAMBER, VARS, CooldownTestCase, Printer, wrap)


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


if __name__ == '__main__':
    unittest.main()
