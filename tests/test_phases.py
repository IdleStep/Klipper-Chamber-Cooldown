"""Phase transitions, completion and what each phase does to heaters and fans."""
import unittest

from test_templates import (
    BED, BED_FANS, CHAMBER, EXHAUST_FAN, EXTERNAL_PC, HARDWARE_VARS, PART_FAN, PROFILES, VARS,
    CooldownTestCase, Printer, wrap)


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


if __name__ == '__main__':
    unittest.main()
