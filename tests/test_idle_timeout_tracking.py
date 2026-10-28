"""idle_timeout_tracking.cfg: remembering and handing back the idle timeout."""
import unittest

from test_templates import (
    VARS, CooldownTestCase, Printer)


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
