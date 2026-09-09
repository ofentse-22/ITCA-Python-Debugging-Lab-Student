"""CLI workflow tests for Backup / Restore."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from itca_training_centre.cli.backup_cli import run_backup_restore_menu
from itca_training_centre.config.settings import ensure_runtime_directories, load_config
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.backup import BACKUP_MANIFEST_FILENAME
from itca_training_centre.services.backup_service import BackupService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.utils.exceptions import RecordNotFoundError


class SequenceClock:
    """Deterministic UTC clock for backup CLI tests."""

    def __init__(self):
        self.current = datetime(2026, 9, 1, 13, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


class SequenceUuidFactory:
    """Deterministic UUID suffix provider for backup CLI tests."""

    def __init__(self):
        self.values = ("aaaaaaaa", "bbbbbbbb", "cccccccc", "dddddddd")
        self.index = 0

    def __call__(self):
        if self.index < len(self.values):
            value = self.values[self.index]
        else:
            value = f"{self.index:08x}"
        self.index += 1
        return value


class BackupCliWorkflowTests(unittest.TestCase):
    def test_menu_can_create_list_inspect_validate_and_return(self):
        with TemporaryDirectory() as temp_dir:
            config, service = self._config_and_service(temp_dir)
            backup_id = "20260901T130000Z_aaaaaaaa"
            choices = iter(["bad", "1", "weekly backup", "2", "3", backup_id, "0"])
            output = []

            run_backup_restore_menu(
                config,
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                service=service,
            )

            joined_output = "\n".join(output)
            self.assertIn("Choose a number from the Backup / Restore menu.", output)
            self.assertIn("Backup created successfully.", output)
            self.assertIn("BACKUPS", output)
            self.assertIn(backup_id, joined_output)
            self.assertIn("Overall: VALID", output)
            self.assertIn("Returning to Main Menu.", output)

    def test_restore_decline_keeps_live_database_then_confirm_restores(self):
        with TemporaryDirectory() as temp_dir:
            config, service = self._config_and_service(temp_dir)
            StudentService(config.paths.database_path).register_student(
                "STU-A001",
                "Original",
                "Student",
            )
            backup = service.create_backup()
            StudentService(config.paths.database_path).register_student(
                "STU-B001",
                "Later",
                "Student",
            )

            decline_output = []
            decline_choices = iter(["4", backup.backup_id, "n", "0"])
            run_backup_restore_menu(
                config,
                input_func=lambda prompt: next(decline_choices),
                output_func=decline_output.append,
                service=service,
            )
            self.assertTrue(_student_exists(config.paths.database_path, "STU-B001"))
            self.assertIn(
                "Restore cancelled. Live database was not changed.",
                decline_output,
            )

            confirm_output = []
            confirm_choices = iter(["4", backup.backup_id, "yes", "0"])
            run_backup_restore_menu(
                config,
                input_func=lambda prompt: next(confirm_choices),
                output_func=confirm_output.append,
                service=service,
            )

            self.assertFalse(_student_exists(config.paths.database_path, "STU-B001"))
            self.assertTrue(_student_exists(config.paths.database_path, "STU-A001"))
            self.assertIn("Restore completed successfully.", confirm_output)
            self.assertIn("Schema version: 1", confirm_output)
            self.assertTrue(
                any(line.startswith("Safety backup ID: ") for line in confirm_output)
            )

    def test_restore_rejects_invalid_missing_and_unsafe_backup_selection(self):
        with TemporaryDirectory() as temp_dir:
            config, service = self._config_and_service(temp_dir)
            backup = service.create_backup()
            manifest_path = backup.backup_path / BACKUP_MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["database_sha256"] = "0" * 64
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            choices = iter(
                [
                    "4",
                    backup.backup_id,
                    "4",
                    "20260901T130900Z_bbbbbbbb",
                    "4",
                    "../outside",
                    "0",
                ]
            )
            output = []

            run_backup_restore_menu(
                config,
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                service=service,
            )

            joined_output = "\n".join(output)
            self.assertIn("Backup is invalid and cannot be restored.", output)
            self.assertIn("Backup was not found: 20260901T130900Z_bbbbbbbb", output)
            self.assertIn("Backup ID is not recognized.", output)
            self.assertNotIn("Traceback", joined_output)
            self.assertNotIn("BackupValidationError", joined_output)

    def _config_and_service(self, temp_dir):
        config = load_config(project_root=Path(temp_dir))
        ensure_runtime_directories(config)
        initialize_database(config.paths.database_path)
        service = BackupService.from_config(
            config,
            clock=SequenceClock(),
            uuid_factory=SequenceUuidFactory(),
        )
        return config, service


def _student_exists(database_path: Path, student_number: str) -> bool:
    try:
        StudentService(database_path).get_student_by_number(student_number)
    except RecordNotFoundError:
        return False
    return True


if __name__ == "__main__":
    unittest.main()
