import unittest

import test_templates  # noqa: F401  (puts Hardware Controls' tests/ on sys.path)
from config_lint import lint
from test_templates import ROOT


class ConfigLint(unittest.TestCase):
    def test_config_files_are_clean(self):
        self.assertEqual(lint(ROOT), {})


if __name__ == '__main__':
    unittest.main()
