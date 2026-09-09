"""CLI workflow tests for Trainer Management and Trainer Assignments."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.app import main


class TrainerCliWorkflowTests(unittest.TestCase):
    def test_trainer_management_full_cli_flow(self):
        choices = iter(
            [
                "4",
                "1",
                "TRN-1001",
                "Thandi",
                "Dlamini",
                "thandi@example.edu",
                "555-1001",
                "3",
                "",
                "2",
                "TRN-1001",
                "4",
                "Thandi",
                "",
                "5",
                "TRN-1001",
                "Thando",
                "",
                "thando@example.edu",
                "",
                "6",
                "TRN-1001",
                "y",
                "3",
                "",
                "3",
                "y",
                "7",
                "TRN-1001",
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
        self.assertIn("Trainer registered successfully: TRN-1001", output)
        self.assertIn("Trainer updated successfully: TRN-1001", output)
        self.assertIn("Trainer is now inactive: TRN-1001", output)
        self.assertIn("Trainer is now active: TRN-1001", output)
        self.assertIn("No trainers found.", output)
        self.assertTrue(any("Thando Dlamini" in line for line in output))
        self.assertTrue(any("inactive" in line for line in output))

    def test_trainer_assignment_full_cli_flow(self):
        choices = iter(
            [
                "2",
                "1",
                "PYF101",
                "Python Fundamentals",
                "",
                "0",
                "active",
                "0",
                "4",
                "1",
                "TRN-1001",
                "Thandi",
                "Dlamini",
                "",
                "",
                "8",
                "1",
                "TRN-1001",
                "PYF101",
                "2026-09-01",
                "2",
                "TRN-1001",
                "",
                "3",
                "PYF101",
                "",
                "4",
                "TRN-1001",
                "",
                "",
                "1",
                "TRN-1001",
                "PYF101",
                "2026-09-02",
                "5",
                "TRN-1001",
                "PYF101",
                "2026-09-30",
                "y",
                "2",
                "TRN-1001",
                "",
                "4",
                "TRN-1001",
                "PYF101",
                "all",
                "6",
                "TRN-1001",
                "PYF101",
                "y",
                "0",
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
        self.assertIn("Trainer assigned successfully: TRN-1001 -> PYF101 (ID 1)", output)
        self.assertIn("Trainer is already actively assigned to this course.", output)
        self.assertIn("Trainer assignment is now ended: ID 1", output)
        self.assertIn("Trainer assignment is now active: ID 1", output)
        self.assertIn("No assignments found for this trainer.", output)
        self.assertTrue(any("TRN-1001 Thandi Dlamini" in line for line in output))
        self.assertTrue(any("PYF101" in line and "Ended" in line for line in output))

    def test_trainer_and_assignment_menus_handle_invalid_input_and_back_flow(self):
        choices = iter(["4", "bad", "8", "bad", "0", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("Choose a number from the Trainer Management menu.", output)
        self.assertIn("Choose a number from the Trainer Assignments menu.", output)
        self.assertIn("Returning to Trainer Management.", output)
        self.assertIn("Returning to Main Menu.", output)

    def test_duplicate_and_missing_trainer_messages_are_user_friendly(self):
        choices = iter(
            [
                "4",
                "1",
                "TRN-1001",
                "Thandi",
                "Dlamini",
                "",
                "",
                "1",
                "trn-1001",
                "Bongi",
                "Mokoena",
                "",
                "",
                "2",
                "TRN-9999",
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
        self.assertIn("Trainer number already exists.", output)
        self.assertIn("No trainer was found for number TRN-9999.", output)


if __name__ == "__main__":
    unittest.main()
