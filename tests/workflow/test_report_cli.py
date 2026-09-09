"""CLI workflow tests for Reports and Statistics."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.app import main
from itca_training_centre.cli.report_cli import run_report_menu
from itca_training_centre.config.settings import ensure_runtime_directories, load_config
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.services.trainer_service import TrainerService
from tests.reporting_helpers import seed_reporting_data


class ReportCliWorkflowTests(unittest.TestCase):
    def _config_with_database(self, temp_dir):
        config = load_config(project_root=Path(temp_dir))
        ensure_runtime_directories(config)
        initialize_database(config.paths.database_path)
        return config

    def test_main_menu_routes_to_reports_menu(self):
        choices = iter(["7", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("REPORTS & STATISTICS", output)
        self.assertIn("Returning to Main Menu.", output)

    def test_reports_menu_displays_all_reports(self):
        with TemporaryDirectory() as temp_dir:
            config = self._config_with_database(temp_dir)
            fixture = seed_reporting_data(config.paths.database_path)
            choices = iter(
                [
                    "1",
                    "2",
                    "STU-1001",
                    "3",
                    "PYF101",
                    "4",
                    "PYF101",
                    "",
                    "",
                    "5",
                    "PYF101",
                    "100",
                    "6",
                    str(fixture.assessment_practical.assessment_id),
                    "7",
                    "TRN-1001",
                    "0",
                ]
            )
            output = []

            run_report_menu(
                config,
                input_func=lambda prompt: next(choices),
                output_func=output.append,
            )

        self.assertIn("System Overview", output)
        self.assertIn("Student Progress Report", output)
        self.assertIn("Course Overview Report", output)
        self.assertIn("Attendance Report", output)
        self.assertIn("Low Attendance Students", output)
        self.assertIn("Assessment Performance Report", output)
        self.assertIn("Trainer Assignment Report", output)
        self.assertTrue(any("STU-1001 Amina Nkosi" in line for line in output))
        self.assertTrue(any("0/100" in line and "Fail" in line for line in output))
        self.assertTrue(any("Missing" in line for line in output))
        self.assertTrue(any("No Calculable Attendance" in line for line in output))
        self.assertTrue(any("PYF101 - Python Fundamentals" in line for line in output))
        self.assertTrue(any("SQL101 - SQLite Basics" in line for line in output))

    def test_reports_menu_handles_invalid_choice_missing_ids_and_thresholds(self):
        with TemporaryDirectory() as temp_dir:
            config = self._config_with_database(temp_dir)
            seed_reporting_data(config.paths.database_path)
            choices = iter(
                [
                    "bad",
                    "2",
                    "STU-404",
                    "3",
                    "MISSING",
                    "4",
                    "PYF101",
                    "2026-09-04",
                    "2026-09-03",
                    "5",
                    "PYF101",
                    "101",
                    "6",
                    "999",
                    "7",
                    "TRN-404",
                    "0",
                ]
            )
            output = []

            run_report_menu(
                config,
                input_func=lambda prompt: next(choices),
                output_func=output.append,
            )

        self.assertIn("Choose a number from the Reports and Statistics menu.", output)
        self.assertIn("No student was found for number STU-404.", output)
        self.assertIn("No course was found for code MISSING.", output)
        self.assertIn("Date from may not be after date to.", output)
        self.assertIn("Attendance threshold must be between 0 and 100.", output)
        self.assertIn("No assessment was found for ID 999.", output)
        self.assertIn("No trainer was found for number TRN-404.", output)

    def test_reports_menu_displays_empty_states_without_raw_python_values(self):
        with TemporaryDirectory() as temp_dir:
            config = self._config_with_database(temp_dir)
            students = StudentService(config.paths.database_path)
            courses = CourseService(config.paths.database_path)
            trainers = TrainerService(config.paths.database_path)
            students.register_student("STU-1001", "Amina", "Nkosi")
            courses.create_course(
                "PYF101",
                "Python Fundamentals",
                fee_amount="0",
                status="active",
            )
            trainers.register_trainer("TRN-1001", "Thandi", "Dlamini")
            choices = iter(
                [
                    "2",
                    "STU-1001",
                    "3",
                    "PYF101",
                    "4",
                    "PYF101",
                    "",
                    "",
                    "5",
                    "PYF101",
                    "80",
                    "7",
                    "TRN-1001",
                    "0",
                ]
            )
            output = []

            run_report_menu(
                config,
                input_func=lambda prompt: next(choices),
                output_func=output.append,
            )

        joined_output = "\n".join(output)
        self.assertIn("No enrolments recorded.", output)
        self.assertIn("No assessments recorded for this course.", output)
        self.assertIn("No attendance sessions found for this course.", output)
        self.assertIn("No students are below this threshold.", output)
        self.assertIn("No course assignments found.", output)
        self.assertNotIn("[]", joined_output)
        self.assertNotIn("{}", joined_output)
        self.assertNotIn("None", joined_output)


if __name__ == "__main__":
    unittest.main()
