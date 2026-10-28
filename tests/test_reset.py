"""COOLDOWN_RESET."""
import unittest

from test_templates import (
    CHAMBER, EXHAUST_FAN, VARS, CooldownTestCase, Printer)


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


if __name__ == '__main__':
    unittest.main()
