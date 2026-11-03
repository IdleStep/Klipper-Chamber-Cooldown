"""install.py edits printer.cfg and moonraker.conf; these tests run its text edits without a printer.

Run with: python -m unittest discover -s tests -v
"""
import importlib.util
import os
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('install', ROOT / 'install.py')
install = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install)

HARDWARE_INCLUDE = '[include Klipper-Hardware-Controls/hardware.cfg]\n'
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

    def test_says_so_when_hardware_controls_is_included_after_it(self):
        text = PRINTER_CFG + '[include Klipper-Chamber-Cooldown/cooldown.cfg]\n' + HARDWARE_INCLUDE
        notes = install.edit_printer_cfg(text, FOLDER)[1]
        self.assertTrue(any('move it above' in note for note in notes))

    def test_says_nothing_about_the_order_when_hardware_controls_comes_first(self):
        text = PRINTER_CFG + HARDWARE_INCLUDE + '[include Klipper-Chamber-Cooldown/cooldown.cfg]\n'
        notes = install.edit_printer_cfg(text, FOLDER)[1]
        self.assertFalse(any('move it above' in note for note in notes))


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


class Files(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = os.path.join(self.folder.name, 'printer.cfg')

    def write_bytes(self, data):
        with open(self.path, 'wb') as f:
            f.write(data)

    def read_bytes(self):
        with open(self.path, 'rb') as f:
            return f.read()

    def test_a_file_with_non_ascii_text_survives_whatever_the_locale_is(self):
        text = '# Query the ID of canbus：\n[display_status]\n# \U0001F4C3 note\n'
        self.write_bytes(b'')
        install.write_text(self.path, text)
        self.assertEqual(install.read_text(self.path), text)
        self.assertEqual(self.read_bytes(), text.encode('utf-8'))

    def test_line_endings_are_kept(self):
        self.write_bytes(b'a\r\nb\r\n')
        install.write_text(self.path, install.read_text(self.path))
        self.assertEqual(self.read_bytes(), b'a\r\nb\r\n')

    def test_writing_leaves_no_temporary_file_behind(self):
        self.write_bytes(b'x\n')
        install.write_text(self.path, 'y\n')
        self.assertEqual(os.listdir(self.folder.name), ['printer.cfg'])


if __name__ == '__main__':
    unittest.main()
