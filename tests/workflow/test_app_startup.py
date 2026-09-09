"""Workflow tests for Phase 1 application startup."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.app import main


class AppStartupWorkflowTests(unittest.TestCase):
    def test_application_exits_cleanly(self):
        with TemporaryDirectory() as temp_dir:
            output = []

            exit_code = main(
                input_func=lambda prompt: "0",
                output_func=output.append,
                project_root=Path(temp_dir),
            )

            self.assertEqual(0, exit_code)
            self.assertIn("Application exited cleanly.", output)

    def test_invalid_menu_choices_retry_until_exit(self):
        with TemporaryDirectory() as temp_dir:
            choices = iter(["abc", "99", "0"])
            output = []

            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

            self.assertEqual(0, exit_code)
            self.assertEqual(2, output.count("Choose a number from the menu."))

    def test_main_menu_routes_to_backup_restore_menu(self):
        with TemporaryDirectory() as temp_dir:
            choices = iter(["9", "0", "0"])
            output = []

            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

            self.assertEqual(0, exit_code)
            self.assertIn("BACKUP / RESTORE", output)
            self.assertIn("Returning to Main Menu.", output)

    def test_startup_creates_controlled_runtime_directories_and_log(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            exit_code = main(
                input_func=lambda prompt: "0",
                output_func=lambda message: None,
                project_root=project_root,
            )

            self.assertEqual(0, exit_code)
            self.assertTrue((project_root / "runtime" / "data").is_dir())
            self.assertTrue((project_root / "runtime" / "logs").is_dir())
            self.assertTrue((project_root / "runtime" / "imports").is_dir())
            self.assertTrue((project_root / "runtime" / "exports").is_dir())
            self.assertTrue(
                (project_root / "runtime" / "logs" / "application.log").exists()
            )
            self.assertTrue(
                (
                    project_root
                    / "runtime"
                    / "data"
                    / "itca_training_centre.sqlite3"
                ).is_file()
            )

    def test_administration_summary_displays_schema_version(self):
        with TemporaryDirectory() as temp_dir:
            choices = iter(["10", "0"])
            output = []

            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

            self.assertEqual(0, exit_code)
            self.assertIn("Schema version    : 1", output)
            self.assertIn("Applied migrations: 1", output)
            self.assertIn("Configuration mode: Read-only summary", output)
            self.assertNotIn("Configuration editing is not implemented in this phase.", output)

    def test_keyboard_interrupt_exits_cleanly_at_application_boundary(self):
        def raise_keyboard_interrupt(prompt):
            raise KeyboardInterrupt

        with TemporaryDirectory() as temp_dir:
            output = []

            exit_code = main(
                input_func=raise_keyboard_interrupt,
                output_func=output.append,
                project_root=Path(temp_dir),
            )

            self.assertEqual(130, exit_code)
            self.assertIn("Application interrupted. Exiting.", output)


if __name__ == "__main__":
    unittest.main()
