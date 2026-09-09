"""Whole-application CLI integration tests for Phase 11."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.app import main


class PhaseElevenCliIntegrationTests(unittest.TestCase):
    def test_main_menu_routes_to_every_completed_application_area(self):
        choices = iter(
            [
                "1",
                "0",
                "2",
                "0",
                "3",
                "0",
                "4",
                "0",
                "5",
                "0",
                "6",
                "0",
                "7",
                "0",
                "8",
                "0",
                "9",
                "0",
                "10",
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
        for menu_label in (
            "1. Student Management",
            "2. Course Management",
            "3. Course Enrolments",
            "4. Trainer Management",
            "5. Attendance Management",
            "6. Assessments and Marks",
            "7. Reports and Statistics",
            "8. Import / Export",
            "9. Backup / Restore",
            "10. Administration / Configuration",
            "0. Exit",
        ):
            self.assertIn(menu_label, output)

        for heading in (
            "Student Management",
            "Course and Module Management",
            "Course Enrolments",
            "Trainer Management",
            "Attendance Management",
            "Assessments and Marks",
            "REPORTS & STATISTICS",
            "IMPORT / EXPORT",
            "BACKUP / RESTORE",
            "Administration / Configuration",
        ):
            self.assertIn(heading, output)

        self.assertFalse(
            any("not implemented" in line.lower() for line in output),
            output,
        )

    def test_cross_domain_cli_walkthrough_reaches_reports_exports_backup_and_admin(self):
        choices = iter(
            [
                "1",
                "1",
                "STU-1101",
                "Lindi",
                "Maseko",
                "lindi@example.test",
                "",
                "0",
                "2",
                "1",
                "PYF111",
                "Python UX",
                "",
                "0",
                "active",
                "8",
                "1",
                "PYF111",
                "MOD-111",
                "CLI Flow",
                "1",
                "",
                "0",
                "0",
                "4",
                "1",
                "TRN-1101",
                "Naledi",
                "Dube",
                "naledi@example.test",
                "",
                "8",
                "1",
                "TRN-1101",
                "PYF111",
                "2026-09-01",
                "0",
                "0",
                "3",
                "1",
                "STU-1101",
                "PYF111",
                "2026-09-01",
                "0",
                "5",
                "1",
                "PYF111",
                "2026-09-02",
                "Kickoff",
                "5",
                "1",
                "STU-1101",
                "present",
                "",
                "9",
                "",
                "STU-1101",
                "",
                "0",
                "6",
                "1",
                "PYF111",
                "MOD-111",
                "CLI Quiz",
                "quiz",
                "10",
                "",
                "5",
                "",
                "5",
                "1",
                "STU-1101",
                "0",
                "Zero mark",
                "8",
                "1",
                "0",
                "7",
                "2",
                "STU-1101",
                "0",
                "8",
                "2",
                "1",
                "0",
                "3",
                "1",
                "0",
                "0",
                "9",
                "1",
                "CLI walkthrough",
                "2",
                "0",
                "10",
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
        for expected in (
            "Student registered successfully: STU-1101",
            "Course registered successfully: PYF111",
            "Module created successfully: MOD-111",
            "Trainer registered successfully: TRN-1101",
            "Student enrolled successfully: STU-1101 -> PYF111 (ID 1)",
            "Trainer assigned successfully: TRN-1101 -> PYF111 (ID 1)",
            "Attendance session created successfully: ID 1",
            "Attendance recorded successfully: ID 1",
            "Assessment created successfully: ID 1",
            "Mark captured successfully: ID 1",
            "Student Progress Report",
            "Students export completed.",
            "System Overview export completed.",
            "Backup created successfully.",
            "Configuration mode: Read-only summary",
            "Application exited cleanly.",
        ):
            self.assertIn(expected, output)

        self.assertIn("Attendance sessions:", output)
        self.assertIn("Assessments:", output)
        self.assertTrue(any("0/10" in line and "Fail" in line for line in output))
        self.assertFalse(any("not implemented" in line.lower() for line in output))
        self.assertFalse(any("Phase " in line for line in output))


if __name__ == "__main__":
    unittest.main()
