"""Tests for CLI table formatting helpers."""

import unittest

from itca_training_centre.cli.tables import format_status, format_title


class TableFormattingTests(unittest.TestCase):
    def test_format_status_uses_user_facing_title_case(self):
        self.assertEqual("Active", format_status("active"))
        self.assertEqual("No Calculable", format_status("no_calculable"))
        self.assertEqual("-", format_status(None))

    def test_format_title_supports_optional_subtitle(self):
        lines = format_title("Application", "Version 1.0")

        self.assertIn("Application", lines)
        self.assertIn("Version 1.0", lines)


if __name__ == "__main__":
    unittest.main()
