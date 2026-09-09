"""CLI workflow tests for Import / Export."""

from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import unittest

from itca_training_centre.app import main
from itca_training_centre.cli.import_export_cli import run_import_export_menu
from itca_training_centre.config.settings import ensure_runtime_directories, load_config
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.services.import_export_service import IMPORT_SCHEMAS
from itca_training_centre.services.student_service import StudentService
from tests.reporting_helpers import seed_reporting_data


class ImportExportCliWorkflowTests(unittest.TestCase):
    def test_main_menu_routes_to_import_export_menu(self):
        choices = iter(["8", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("IMPORT / EXPORT", output)
        self.assertIn("Returning to Main Menu.", output)

    def test_import_preview_can_be_declined_without_creating_students(self):
        with TemporaryDirectory() as temp_dir:
            config = self._config_with_database(temp_dir)
            self._write_import_csv(
                config,
                "students.csv",
                IMPORT_SCHEMAS["students"].headers,
                [
                    {
                        "student_number": "STU-9001",
                        "first_name": "Amina",
                        "last_name": "Nkosi",
                        "email": "",
                        "phone": "",
                    }
                ],
            )
            choices = iter(["1", "1", "students.csv", "n", "0", "0"])
            output = []

            run_import_export_menu(
                config,
                input_func=lambda prompt: next(choices),
                output_func=output.append,
            )

            self.assertIn("Students Import Preview", output)
            self.assertIn("Import cancelled. No data was imported.", output)
            self.assertEqual([], StudentService(config.paths.database_path).list_students())

    def test_import_preview_can_be_confirmed(self):
        with TemporaryDirectory() as temp_dir:
            config = self._config_with_database(temp_dir)
            self._write_import_csv(
                config,
                "students.csv",
                IMPORT_SCHEMAS["students"].headers,
                [
                    {
                        "student_number": "STU-9002",
                        "first_name": "Bongi",
                        "last_name": "Mokoena",
                        "email": "",
                        "phone": "",
                    }
                ],
            )
            choices = iter(["1", "1", "students.csv", "yes", "0", "0"])
            output = []

            run_import_export_menu(
                config,
                input_func=lambda prompt: next(choices),
                output_func=output.append,
            )

            students = StudentService(config.paths.database_path).list_students()
            self.assertIn("Import completed: 1 record(s) created.", output)
            self.assertEqual(["STU-9002"], [student.student_number for student in students])

    def test_import_menu_displays_missing_malformed_and_conflict_issues(self):
        with TemporaryDirectory() as temp_dir:
            config = self._config_with_database(temp_dir)
            StudentService(config.paths.database_path).register_student(
                "STU-9101",
                "Existing",
                "Student",
            )
            (config.paths.import_dir / "malformed.csv").write_text(
                'student_number,first_name,last_name,email,phone\n"STU-9100,Amina\n',
                encoding="utf-8",
                newline="",
            )
            self._write_import_csv(
                config,
                "conflict.csv",
                IMPORT_SCHEMAS["students"].headers,
                [
                    {
                        "student_number": "STU-9101",
                        "first_name": "Again",
                        "last_name": "Student",
                        "email": "",
                        "phone": "",
                    }
                ],
            )
            choices = iter(
                [
                    "1",
                    "1",
                    "missing.csv",
                    "1",
                    "malformed.csv",
                    "1",
                    "conflict.csv",
                    "0",
                    "0",
                ]
            )
            output = []

            run_import_export_menu(
                config,
                input_func=lambda prompt: next(choices),
                output_func=output.append,
            )

            joined_output = "\n".join(output)
            self.assertIn("Import file was not found", joined_output)
            self.assertIn("CSV file is malformed", joined_output)
            self.assertIn("Row 2:", output)
            self.assertIn("  student_number: Student number already exists.", output)

    def test_export_and_recent_file_cli_flows(self):
        with TemporaryDirectory() as temp_dir:
            config = self._config_with_database(temp_dir)
            seed_reporting_data(config.paths.database_path)
            choices = iter(["bad", "2", "1", "0", "3", "1", "0", "4", "0"])
            output = []

            run_import_export_menu(
                config,
                input_func=lambda prompt: next(choices),
                output_func=output.append,
            )

            joined_output = "\n".join(output)
            self.assertIn("Choose a number from the Import / Export menu.", output)
            self.assertIn("Students export completed.", output)
            self.assertIn("System Overview export completed.", output)
            self.assertIn("RECENT EXPORT FILES", output)
            self.assertIn(".csv", joined_output)
            self.assertIn(".txt", joined_output)

    def test_report_export_prompts_display_not_found_without_raw_repr(self):
        with TemporaryDirectory() as temp_dir:
            config = self._config_with_database(temp_dir)
            seed_reporting_data(config.paths.database_path)
            choices = iter(["3", "2", "STU-404", "0", "0"])
            output = []

            run_import_export_menu(
                config,
                input_func=lambda prompt: next(choices),
                output_func=output.append,
            )

            joined_output = "\n".join(output)
            self.assertIn("No student was found for number STU-404.", output)
            self.assertNotIn("RecordNotFoundError", joined_output)
            self.assertNotIn("Traceback", joined_output)

    def _config_with_database(self, temp_dir):
        config = load_config(project_root=Path(temp_dir))
        ensure_runtime_directories(config)
        initialize_database(config.paths.database_path)
        return config

    def _write_import_csv(
        self,
        config,
        filename: str,
        headers: tuple[str, ...],
        rows: list[dict[str, object]],
    ) -> Path:
        path = config.paths.import_dir / filename
        with open(path, "w", encoding="utf-8", newline="") as file_object:
            writer = csv.DictWriter(file_object, fieldnames=list(headers))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path


if __name__ == "__main__":
    unittest.main()
