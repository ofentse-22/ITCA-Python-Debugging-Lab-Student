"""CLI workflow tests for Assessments and Marks."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.app import main


class AssessmentCliWorkflowTests(unittest.TestCase):
    def test_assessment_management_full_cli_flow(self):
        choices = iter(
            [
                "1",
                "1",
                "STU-1001",
                "Amina",
                "Nkosi",
                "",
                "",
                "1",
                "STU-1002",
                "Bongi",
                "Mokoena",
                "",
                "",
                "1",
                "STU-1003",
                "Celia",
                "Zulu",
                "",
                "",
                "0",
                "2",
                "1",
                "PYF101",
                "Python Fundamentals",
                "",
                "0",
                "active",
                "8",
                "1",
                "PYF101",
                "MOD-101",
                "Variables",
                "1",
                "",
                "0",
                "0",
                "3",
                "1",
                "STU-1001",
                "PYF101",
                "2026-09-01",
                "1",
                "STU-1002",
                "PYF101",
                "2026-09-01",
                "0",
                "6",
                "1",
                "PYF101",
                "MOD-101",
                "Variables Practical",
                "practical",
                "10",
                "25",
                "5",
                "",
                "1",
                "MISSING",
                "",
                "Missing Course Assessment",
                "quiz",
                "10",
                "",
                "",
                "",
                "1",
                "PYF101",
                "",
                "Bad Maximum",
                "quiz",
                "0",
                "",
                "",
                "",
                "2",
                "1",
                "3",
                "Variables",
                "PYF101",
                "MOD-101",
                "",
                "",
                "n",
                "5",
                "1",
                "STU-1003",
                "5",
                "",
                "5",
                "1",
                "STU-1001",
                "10.5",
                "",
                "5",
                "1",
                "STU-1001",
                "0",
                "Zero recorded",
                "5",
                "1",
                "STU-1001",
                "5",
                "",
                "6",
                "1",
                "8",
                "Good work",
                "",
                "y",
                "8",
                "1",
                "7",
                "1",
                "STU-1002",
                "9",
                "Corrected upward",
                "9",
                "STU-1002",
                "",
                "10",
                "1",
                "11",
                "1",
                "y",
                "12",
                "1",
                "0",
                "0",
            ]
        )

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("Assessment created successfully: ID 1", output)
        self.assertIn("No course was found for code MISSING.", output)
        self.assertIn("Maximum mark must be greater than zero.", output)
        self.assertIn(
            "Student STU-1003 is not eligible for assessment 1.",
            output,
        )
        self.assertIn("Mark must be between 0 and 10 for this assessment.", output)
        self.assertIn("Mark captured successfully: ID 1", output)
        self.assertIn(
            "Result is already recorded for this student and assessment.",
            output,
        )
        self.assertIn("Class marks captured successfully: 1 records", output)
        self.assertIn("Mark corrected successfully: ID 2", output)
        self.assertIn("Assessment archived successfully: ID 1", output)
        self.assertIn("Assessment reactivated successfully: ID 1", output)
        self.assertIn("Assessments:", output)
        self.assertTrue(any("Variables Practical" in line for line in output))
        self.assertTrue(any("STU-1001 Amina Nkosi" in line and "0.00%" in line for line in output))
        self.assertTrue(any("90.00%" in line for line in output))
        self.assertTrue(any("Pass rate" in line and "50.00%" in line for line in output))

    def test_assessment_menu_invalid_input_and_back_flow(self):
        choices = iter(["6", "bad", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("Choose a number from the Assessments and Marks menu.", output)
        self.assertIn("Returning to Main Menu.", output)

    def test_missing_assessment_message_is_user_friendly(self):
        choices = iter(["6", "2", "99", "10", "99", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(2, output.count("No assessment was found for ID 99."))


if __name__ == "__main__":
    unittest.main()
