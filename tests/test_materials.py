"""Material selection and COOLDOWN_SELECT."""
import unittest

from test_templates import (
    MATERIALS, VARS, CooldownTestCase, Printer)


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


if __name__ == '__main__':
    unittest.main()
