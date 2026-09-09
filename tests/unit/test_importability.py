"""Import smoke tests for Phase 1 packages."""

import importlib
from pathlib import Path
import subprocess
import sys
import unittest


class ImportabilityTests(unittest.TestCase):
    def test_phase_one_modules_import(self):
        module_names = [
            "itca_training_centre",
            "itca_training_centre.__main__",
            "itca_training_centre.app",
            "itca_training_centre.cli.assessment_cli",
            "itca_training_centre.cli.attendance_cli",
            "itca_training_centre.cli.backup_cli",
            "itca_training_centre.cli.course_cli",
            "itca_training_centre.cli.enrolment_cli",
            "itca_training_centre.cli.import_export_cli",
            "itca_training_centre.cli.main_menu",
            "itca_training_centre.cli.prompts",
            "itca_training_centre.cli.report_cli",
            "itca_training_centre.cli.student_cli",
            "itca_training_centre.cli.tables",
            "itca_training_centre.cli.trainer_cli",
            "itca_training_centre.config.defaults",
            "itca_training_centre.config.settings",
            "itca_training_centre.data",
            "itca_training_centre.data.connection",
            "itca_training_centre.data.decimal_storage",
            "itca_training_centre.data.migrations",
            "itca_training_centre.data.schema",
            "itca_training_centre.models",
            "itca_training_centre.models.assessment",
            "itca_training_centre.models.attendance_record",
            "itca_training_centre.models.attendance_session",
            "itca_training_centre.models.backup",
            "itca_training_centre.models.course",
            "itca_training_centre.models.course_enrolment",
            "itca_training_centre.models.import_export",
            "itca_training_centre.models.module",
            "itca_training_centre.models.mark",
            "itca_training_centre.models.reports",
            "itca_training_centre.models.student",
            "itca_training_centre.models.trainer",
            "itca_training_centre.models.trainer_assignment",
            "itca_training_centre.repositories",
            "itca_training_centre.repositories.assessment_repository",
            "itca_training_centre.repositories.attendance_record_repository",
            "itca_training_centre.repositories.attendance_session_repository",
            "itca_training_centre.repositories.course_enrolment_repository",
            "itca_training_centre.repositories.course_repository",
            "itca_training_centre.repositories.import_export_repository",
            "itca_training_centre.repositories.module_repository",
            "itca_training_centre.repositories.mark_repository",
            "itca_training_centre.repositories.report_repository",
            "itca_training_centre.repositories.student_repository",
            "itca_training_centre.repositories.trainer_assignment_repository",
            "itca_training_centre.repositories.trainer_repository",
            "itca_training_centre.services",
            "itca_training_centre.services.assessment_service",
            "itca_training_centre.services.attendance_service",
            "itca_training_centre.services.backup_service",
            "itca_training_centre.services.course_enrolment_service",
            "itca_training_centre.services.course_service",
            "itca_training_centre.services.import_export_service",
            "itca_training_centre.services.module_service",
            "itca_training_centre.storage",
            "itca_training_centre.storage.backup_storage",
            "itca_training_centre.storage.csv_io",
            "itca_training_centre.storage.text_export",
            "itca_training_centre.services.report_service",
            "itca_training_centre.services.student_service",
            "itca_training_centre.services.trainer_assignment_service",
            "itca_training_centre.services.trainer_service",
            "itca_training_centre.utils.exceptions",
            "itca_training_centre.utils.logging_setup",
            "itca_training_centre.utils.path_safety",
            "itca_training_centre.utils.validators",
        ]

        for module_name in module_names:
            with self.subTest(module_name=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))

    def test_cli_modules_import_cleanly_in_fresh_interpreters(self):
        project_root = Path(__file__).resolve().parents[2]
        module_names = (
            "itca_training_centre.cli.report_cli",
            "itca_training_centre.cli.import_export_cli",
        )

        for module_name in module_names:
            with self.subTest(module_name=module_name):
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        "-c",
                        f"import importlib; importlib.import_module({module_name!r})",
                    ],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)


if __name__ == "__main__":
    unittest.main()
