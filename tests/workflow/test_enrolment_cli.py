"""CLI workflow tests for Course Enrolments."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.app import main


class EnrolmentCliWorkflowTests(unittest.TestCase):
    def test_course_enrolment_full_cli_flow(self):
        choices = iter(
            [
                "1",
                "1",
                "STU-1001",
                "Amina",
                "Nkosi",
                "amina@example.edu",
                "",
                "0",
                "2",
                "1",
                "PYF101",
                "Python Fundamentals",
                "",
                "0",
                "active",
                "0",
                "3",
                "1",
                "STU-1001",
                "PYF101",
                "2026-09-01",
                "2",
                "STU-1001",
                "",
                "3",
                "PYF101",
                "",
                "4",
                "STU-1001",
                "",
                "",
                "1",
                "STU-1001",
                "PYF101",
                "2026-09-02",
                "5",
                "STU-1001",
                "PYF101",
                "2026-09-15",
                "Student withdrew",
                "y",
                "2",
                "STU-1001",
                "",
                "4",
                "STU-1001",
                "PYF101",
                "all",
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
        self.assertIn("Student enrolled successfully: STU-1001 -> PYF101 (ID 1)", output)
        self.assertIn("Student is already actively enrolled in this course.", output)
        self.assertIn("Course enrolment cancelled: ID 1", output)
        self.assertIn("No enrolments found for this student.", output)
        self.assertTrue(any("STU-1001 Amina Nkosi" in line for line in output))
        self.assertTrue(any("PYF101" in line and "Cancelled" in line for line in output))

    def test_enrolment_menu_invalid_input_and_back_flow(self):
        choices = iter(["3", "bad", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("Choose a number from the Course Enrolments menu.", output)
        self.assertIn("Returning to Main Menu.", output)

    def test_missing_student_or_course_messages_are_user_friendly(self):
        choices = iter(
            [
                "3",
                "1",
                "STU-9999",
                "PYF101",
                "2026-09-01",
                "2",
                "STU-9999",
                "",
                "3",
                "MISSING",
                "",
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
        self.assertIn("No student was found for number STU-9999.", output)
        self.assertIn("No course was found for code MISSING.", output)


if __name__ == "__main__":
    unittest.main()
