"""install.py edits printer.cfg and moonraker.conf; these tests run its text edits without a printer.

Run with: python -m unittest discover -s tests -v
"""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('install', ROOT / 'install.py')
install = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install)

FOLDER = 'Klipper-Chamber-Cooldown'
PRINTER_CFG = '[respond]\n\n[stepper_x]\nstep_pin: PB13\n'
SAVED = '#*# <---------------------- SAVE_CONFIG ---------------------->\n#*# [stepper_x]\n'
MOONRAKER = '[server]\nhost: 0.0.0.0\n'


class PrinterCfg(unittest.TestCase):
    def test_adds_the_include_after_the_existing_sections(self):
        new, notes = install.edit_printer_cfg(PRINTER_CFG, FOLDER)
        self.assertTrue(new.startswith(PRINTER_CFG))
        self.assertIn('[include Klipper-Chamber-Cooldown/cooldown.cfg]\n[include cooldown-local.cfg]', new)
        self.assertEqual(notes, ['added the includes for Klipper-Chamber-Cooldown'])

    def test_adds_the_include_above_the_saved_config(self):
        new, _ = install.edit_printer_cfg(PRINTER_CFG + '\n' + SAVED, FOLDER)
        self.assertLess(new.index('cooldown.cfg'), new.index('SAVE_CONFIG'))
        self.assertTrue(new.endswith(SAVED))

    def test_running_it_again_changes_nothing(self):
        once, _ = install.edit_printer_cfg(PRINTER_CFG, FOLDER)
        twice, notes = install.edit_printer_cfg(once, FOLDER)
        self.assertEqual(once, twice)
        self.assertEqual(notes, ['printer.cfg already includes Klipper-Chamber-Cooldown'])

    def test_a_hand_written_include_is_left_alone(self):
        text = PRINTER_CFG + '[include Klipper-Chamber-Cooldown/fans.cfg]\n'
        self.assertEqual(install.edit_printer_cfg(text, FOLDER)[0], text)

    def test_a_commented_include_does_not_count(self):
        text = PRINTER_CFG + '#[include Klipper-Chamber-Cooldown/cooldown.cfg]\n'
        self.assertIn(install.BEGIN, install.edit_printer_cfg(text, FOLDER)[0])

    def test_removing_the_block_restores_the_file(self):
        for original in (PRINTER_CFG, PRINTER_CFG + '\n' + SAVED):
            new, _ = install.edit_printer_cfg(original, FOLDER)
            self.assertEqual(install.remove_block(new), original)


class Moonraker(unittest.TestCase):
    ARGS = ('~/printer_data/config/Klipper-Chamber-Cooldown',
            'https://github.com/IdleStep/Klipper-Chamber-Cooldown.git')

    def test_adds_the_update_section(self):
        new, _ = install.edit_moonraker(MOONRAKER, *self.ARGS, 'stable')
        for line in ('[update_manager Klipper-Chamber-Cooldown]', 'channel: stable',
                     'path: ~/printer_data/config/Klipper-Chamber-Cooldown',
                     'managed_services: klipper'):
            self.assertIn(line, new)

    def test_follows_main_on_the_dev_channel(self):
        self.assertIn('channel: dev', install.edit_moonraker(MOONRAKER, *self.ARGS, 'dev')[0])

    def test_running_it_again_changes_nothing(self):
        once, _ = install.edit_moonraker(MOONRAKER, *self.ARGS, 'stable')
        self.assertEqual(install.edit_moonraker(once, *self.ARGS, 'stable')[0], once)

    def test_a_hand_written_section_is_left_alone(self):
        text = MOONRAKER + '\n[update_manager Klipper-Chamber-Cooldown]\ntype: git_repo\n'
        self.assertEqual(install.edit_moonraker(text, *self.ARGS, 'stable')[0], text)

    def test_removing_the_block_restores_the_file(self):
        new, _ = install.edit_moonraker(MOONRAKER, *self.ARGS, 'stable')
        self.assertEqual(install.remove_block(new), MOONRAKER)


class ReleaseTags(unittest.TestCase):
    def test_newest_first_by_number_not_by_text(self):
        self.assertEqual(install.release_tags('v3.9.0 v3.10.0 v2.0.0'), ['v3.10.0', 'v3.9.0', 'v2.0.0'])

    def test_other_tags_are_ignored(self):
        self.assertEqual(install.release_tags('v3.4.0 v3.5.0-rc1 nightly'), ['v3.4.0'])


if __name__ == '__main__':
    unittest.main()
