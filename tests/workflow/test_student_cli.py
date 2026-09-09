"""CLI workflow tests for Student Management."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.app import main


class StudentCliWorkflowTests(unittest.TestCase):
    def test_student_management_full_cli_flow(self):
        choices = iter(
            [
                "1",
                "1",
                "STU-1001",
                "Amina",
                "Nkosi",
                "amina.nkosi@example.edu",
                "555-0101",
                "3",
                "",
                "2",
                "STU-1001",
                "4",
                "Amina",
                "",
                "5",
                "STU-1001",
                "Amira",
                "",
                "amira@example.edu",
                "",
                "6",
                "STU-1001",
                "y",
                "3",
                "",
                "3",
                "y",
                "7",
                "STU-1001",
                "y",
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
        self.assertIn("Student registered successfully: STU-1001", output)
        self.assertIn("Student updated successfully: STU-1001", output)
        self.assertIn("Student is now inactive: STU-1001", output)
        self.assertIn("Student is now active: STU-1001", output)
        self.assertIn("No students found.", output)
        self.assertTrue(any("Amira Nkosi" in line for line in output))
        self.assertTrue(any("inactive" in line for line in output))

    def test_student_menu_invalid_input_and_back_flow(self):
        choices = iter(["1", "bad", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("Choose a number from the Student Management menu.", output)
        self.assertIn("Returning to Main Menu.", output)

    def test_registration_can_be_cancelled(self):
        choices = iter(["1", "1", "q", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("Student registration cancelled.", output)

    def test_duplicate_identifier_message_is_user_friendly(self):
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
                "STU-1001",
                "Bongi",
                "Mokoena",
                "",
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
        self.assertIn("Student number already exists.", output)

    def test_missing_student_message_is_user_friendly(self):
        choices = iter(["1", "2", "STU-9999", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("No student was found for number STU-9999.", output)


if __name__ == "__main__":
    unittest.main()
