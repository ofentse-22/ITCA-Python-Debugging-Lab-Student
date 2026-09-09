"""CLI workflow tests for Course and Module Management."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.app import main


class CourseCliWorkflowTests(unittest.TestCase):
    def test_course_management_full_cli_flow(self):
        choices = iter(
            [
                "2",
                "1",
                "PYF101",
                "Python Fundamentals",
                "Core Python skills",
                "1500.50",
                "active",
                "3",
                "",
                "2",
                "PYF101",
                "4",
                "Python",
                "",
                "5",
                "PYF101",
                "Python Essentials",
                "",
                "1750",
                "",
                "6",
                "PYF101",
                "y",
                "3",
                "archived",
                "7",
                "PYF101",
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
        self.assertIn("Course registered successfully: PYF101", output)
        self.assertIn("Course updated successfully: PYF101", output)
        self.assertIn("Course is now archived: PYF101", output)
        self.assertIn("Course is now active: PYF101", output)
        self.assertIn("No modules found for this course.", output)
        self.assertTrue(any("Python Essentials" in line for line in output))
        self.assertTrue(any("archived" in line for line in output))

    def test_module_management_full_cli_flow(self):
        choices = iter(
            [
                "2",
                "1",
                "PYF101",
                "Python Fundamentals",
                "",
                "0",
                "active",
                "1",
                "SQL101",
                "SQLite Basics",
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
                "1",
                "PYF101",
                "MOD-201",
                "Loops",
                "2",
                "",
                "1",
                "SQL101",
                "MOD-101",
                "Relational Tables",
                "1",
                "",
                "3",
                "PYF101",
                "",
                "2",
                "PYF101",
                "MOD-101",
                "4",
                "MOD-101",
                "",
                "",
                "5",
                "PYF101",
                "MOD-101",
                "Variables and Operators",
                "3",
                "",
                "1",
                "PYF101",
                "MOD-201",
                "Duplicate Loops",
                "4",
                "",
                "6",
                "PYF101",
                "MOD-101",
                "y",
                "3",
                "PYF101",
                "archived",
                "7",
                "PYF101",
                "MOD-101",
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
        self.assertEqual(2, output.count("Module created successfully: MOD-101"))
        self.assertIn("Module created successfully: MOD-201", output)
        self.assertIn("Module updated successfully: MOD-101", output)
        self.assertIn("Module code already exists for this course.", output)
        self.assertIn("Module is now archived: MOD-101", output)
        self.assertIn("Module is now active: MOD-101", output)
        self.assertTrue(any("PYF101 - Python Fundamentals" in line for line in output))
        self.assertTrue(any("Variables and Operators" in line for line in output))

    def test_course_menu_invalid_input_and_back_flow(self):
        choices = iter(["2", "bad", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("Choose a number from the Course Management menu.", output)
        self.assertIn("Returning to Main Menu.", output)

    def test_module_menu_invalid_input_and_back_flow(self):
        choices = iter(["2", "8", "bad", "0", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("Choose a number from the Module Management menu.", output)
        self.assertIn("Returning to Course Management.", output)

    def test_duplicate_course_code_message_is_user_friendly(self):
        choices = iter(
            [
                "2",
                "1",
                "PYF101",
                "Python Fundamentals",
                "",
                "0",
                "active",
                "1",
                "PYF101",
                "Python Essentials",
                "",
                "0",
                "active",
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
        self.assertIn("Course code already exists.", output)

    def test_missing_course_message_is_user_friendly(self):
        choices = iter(["2", "2", "MISSING", "0", "0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertIn("No course was found for code MISSING.", output)

    def test_missing_parent_course_for_module_is_user_friendly(self):
        choices = iter(
            [
                "2",
                "8",
                "1",
                "MISSING",
                "MOD-101",
                "Variables",
                "1",
                "",
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
        self.assertIn("No course was found for code MISSING.", output)


if __name__ == "__main__":
    unittest.main()
