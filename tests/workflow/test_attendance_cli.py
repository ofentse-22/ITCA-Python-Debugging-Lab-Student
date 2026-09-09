"""CLI workflow tests for Attendance Management."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.app import main


class AttendanceCliWorkflowTests(unittest.TestCase):
    def test_attendance_management_full_cli_flow(self):
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
                "5",
                "1",
                "PYF101",
                "2026-09-02",
                "Control Flow",
                "1",
                "PYF101",
                "2026-09-02",
                "Control Flow",
                "3",
                "PYF101",
                "2026-09-01",
                "2026-09-03",
                "flow",
                "4",
                "1",
                "absent",
                "Travel",
                "present",
                "",
                "y",
                "5",
                "1",
                "STU-1003",
                "present",
                "",
                "5",
                "1",
                "STU-1001",
                "present",
                "",
                "7",
                "1",
                "6",
                "1",
                "STU-1002",
                "late",
                "Arrived late",
                "7",
                "1",
                "1",
                "PYF101",
                "2026-09-03",
                "Loops",
                "5",
                "2",
                "STU-1001",
                "absent",
                "Sick",
                "8",
                "STU-1001",
                "",
                "9",
                "",
                "STU-1001",
                "",
                "9",
                "low",
                "PYF101",
                "80",
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
        self.assertIn("Attendance session created successfully: ID 1", output)
        self.assertIn(
            "Attendance session already exists for this course, date, and topic.",
            output,
        )
        self.assertIn("Class attendance recorded successfully: 2 records", output)
        self.assertIn("Student STU-1003 is not eligible for attendance in session 1.", output)
        self.assertIn(
            "Attendance is already recorded for this student and session.",
            output,
        )
        self.assertIn("Attendance record updated successfully: ID 1", output)
        self.assertIn("Attendance recorded successfully: ID 3", output)
        self.assertIn("Attendance sessions:", output)
        self.assertTrue(any("Control Flow" in line for line in output))
        self.assertTrue(any("STU-1002 Bongi Mokoena" in line and "Late" in line for line in output))
        self.assertTrue(any("STU-1001 Amina Nkosi" in line and "50.00%" in line for line in output))

    def test_attendance_menu_invalid_input_and_back_flow(self):
        choices = iter(["5", "bad", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("Choose a number from the Attendance Management menu.", output)
        self.assertIn("Returning to Main Menu.", output)

    def test_missing_course_and_session_messages_are_user_friendly(self):
        choices = iter(
            [
                "5",
                "1",
                "MISSING",
                "2026-09-01",
                "Control Flow",
                "2",
                "99",
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
        self.assertIn("No course was found for code MISSING.", output)
        self.assertIn("No attendance session was found for ID 99.", output)


if __name__ == "__main__":
    unittest.main()
