"""Integration tests for BackupService."""

from datetime import datetime, timedelta, timezone
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import unittest

from itca_training_centre.config.settings import ensure_runtime_directories, load_config
from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.data.schema import LATEST_SCHEMA_VERSION
from itca_training_centre.models.backup import (
    BACKUP_CONFIG_FILENAME,
    BACKUP_DATABASE_FILENAME,
    BACKUP_FORMAT_VERSION,
    BACKUP_MANIFEST_FILENAME,
    BACKUP_REASON_PRE_RESTORE,
)
from itca_training_centre.services.assessment_service import AssessmentService
from itca_training_centre.services.course_enrolment_service import CourseEnrolmentService
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.backup_service import BackupService
from itca_training_centre.services.module_service import ModuleService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.services.trainer_assignment_service import (
    TrainerAssignmentService,
)
from itca_training_centre.services.trainer_service import TrainerService
from itca_training_centre.storage.backup_storage import sha256_file
from itca_training_centre.utils.exceptions import (
    BackupError,
    BackupValidationError,
    RestoreError,
    ValidationError,
)
from tests.reporting_helpers import OPERATIONAL_TABLES, seed_reporting_data


class SequenceClock:
    """Deterministic UTC clock for backup IDs and manifests."""

    def __init__(self):
        self.current = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


class SequenceUuidFactory:
    """Deterministic UUID suffix provider for tests."""

    def __init__(self):
        self.values = [
            "aaaaaaaa",
            "bbbbbbbb",
            "cccccccc",
            "dddddddd",
            "eeeeeeee",
            "ffffffff",
        ]
        self.index = 0

    def __call__(self):
        if self.index < len(self.values):
            value = self.values[self.index]
        else:
            value = f"{self.index:08x}"
        self.index += 1
        return value


class ListLogger:
    """Small logger test double that records application events."""

    def __init__(self):
        self.messages = []

    def info(self, message, *args, **kwargs):
        self.messages.append(("info", message))

    def warning(self, message, *args, **kwargs):
        self.messages.append(("warning", message))

    def exception(self, message, *args, **kwargs):
        self.messages.append(("exception", message))


class BackupServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = TemporaryDirectory()
        self.project_root = Path(self.temp_context.__enter__())
        self.config = load_config(project_root=self.project_root)
        ensure_runtime_directories(self.config)
        initialize_database(self.config.paths.database_path)
        self.clock = SequenceClock()
        self.uuid_factory = SequenceUuidFactory()

    def tearDown(self):
        self.temp_context.__exit__(None, None, None)

    def test_empty_database_backup_records_manifest_and_validates(self):
        service = self._service()
        before_state = _database_state(self.config.paths.database_path)

        backup = service.create_backup(reason="daily check")
        validation = service.validate_backup(backup.backup_id)
        manifest = _read_manifest(backup.backup_path)

        self.assertTrue(backup.is_valid)
        self.assertTrue(validation.valid)
        self.assertEqual(BACKUP_FORMAT_VERSION, manifest["backup_format_version"])
        self.assertEqual(backup.backup_id, manifest["backup_id"])
        self.assertEqual("2026-09-01T12:00:00Z", manifest["created_at"])
        self.assertEqual(LATEST_SCHEMA_VERSION, manifest["schema_version"])
        self.assertEqual([1], manifest["migration_versions"])
        self.assertEqual(BACKUP_DATABASE_FILENAME, manifest["database_filename"])
        self.assertNotIn(str(self.project_root), json.dumps(manifest))
        self.assertNotIn("Jean", json.dumps(manifest))
        self.assertEqual(
            backup.database_path.stat().st_size,
            manifest["database_size_bytes"],
        )
        self.assertEqual(sha256_file(backup.database_path), manifest["database_sha256"])
        self.assertEqual(before_state, _database_state(self.config.paths.database_path))

    def test_populated_backups_are_consistent_unique_and_read_only(self):
        service = self._service()
        self._seed_decimal_state()
        state_at_backup = _database_state(self.config.paths.database_path)

        first_backup = service.create_backup()
        second_backup = service.create_backup()
        StudentService(self.config.paths.database_path).register_student(
            "STU-9000",
            "Later",
            "Student",
        )

        self.assertNotEqual(first_backup.backup_id, second_backup.backup_id)
        self.assertRegex(
            first_backup.backup_id,
            r"^20260901T120000Z_[a-f0-9]{8}$",
        )
        self.assertEqual(state_at_backup, _database_state(first_backup.database_path))
        self.assertNotEqual(state_at_backup, _database_state(self.config.paths.database_path))

        backup_sha = sha256_file(first_backup.database_path)
        live_state_after_mutation = _database_state(self.config.paths.database_path)
        service.list_backups()
        service.inspect_backup(first_backup.backup_id)
        service.validate_backup(first_backup.backup_id)

        self.assertEqual(backup_sha, sha256_file(first_backup.database_path))
        self.assertEqual(live_state_after_mutation, _database_state(self.config.paths.database_path))

    def test_failed_backup_creation_cleans_incomplete_temp_directory(self):
        service = self._service()

        def fail_config_snapshot(backup_path):
            raise BackupError("forced config failure")

        service._copy_config_snapshot = fail_config_snapshot

        with self.assertRaises(BackupError):
            service.create_backup()

        artifacts = tuple(self.config.paths.backup_dir.iterdir())
        self.assertEqual((), artifacts)

    def test_list_backups_orders_newest_and_handles_artifacts(self):
        service = self._service()

        self.assertEqual((), service.list_backups())
        first_backup = service.create_backup()
        second_backup = service.create_backup()
        (self.config.paths.backup_dir / ".tmp_backup_20260901T120200Z_deadbeef").mkdir()
        (self.config.paths.backup_dir / "unrelated.txt").write_text("ignore", encoding="utf-8")

        malformed_id = "20260901T120300Z_1234abcd"
        malformed_dir = self.config.paths.backup_dir / f"backup_{malformed_id}"
        malformed_dir.mkdir()
        (malformed_dir / BACKUP_MANIFEST_FILENAME).write_text("{not json", encoding="utf-8")
        (malformed_dir / BACKUP_DATABASE_FILENAME).write_bytes(b"not sqlite")

        backups = service.list_backups()

        self.assertEqual(
            [malformed_id, second_backup.backup_id, first_backup.backup_id],
            [backup.backup_id for backup in backups],
        )
        self.assertFalse(backups[0].is_valid)

    def test_validation_rejects_corrupted_and_tampered_backup_packages(self):
        service = self._service()
        self._seed_decimal_state()

        valid_backup = service.create_backup()
        self.assertTrue(service.validate_backup(valid_backup.backup_id).valid)

        checksum_backup = service.create_backup()
        manifest = _read_manifest(checksum_backup.backup_path)
        manifest["database_sha256"] = "0" * 64
        _write_manifest(checksum_backup.backup_path, manifest)
        checksum_result = service.validate_backup(checksum_backup.backup_id)
        self.assertFalse(checksum_result.valid)
        self.assertFalse(checksum_result.checksum_valid)

        missing_db_backup = service.create_backup()
        missing_db_backup.database_path.unlink()
        missing_db_result = service.validate_backup(missing_db_backup.backup_id)
        self.assertFalse(missing_db_result.valid)
        self.assertIn("Backup database file was not found.", missing_db_result.issues)

        invalid_json_backup = service.create_backup()
        (invalid_json_backup.backup_path / BACKUP_MANIFEST_FILENAME).write_text(
            "{bad",
            encoding="utf-8",
        )
        invalid_json_result = service.validate_backup(invalid_json_backup.backup_id)
        self.assertFalse(invalid_json_result.valid)
        self.assertIn("Backup manifest is invalid JSON.", invalid_json_result.issues)

        future_format_backup = service.create_backup()
        manifest = _read_manifest(future_format_backup.backup_path)
        manifest["backup_format_version"] = BACKUP_FORMAT_VERSION + 1
        _write_manifest(future_format_backup.backup_path, manifest)
        future_result = service.validate_backup(future_format_backup.backup_id)
        self.assertFalse(future_result.valid)
        self.assertIn("Unsupported backup format version", future_result.message)

        non_sqlite_backup = service.create_backup()
        non_sqlite_backup.database_path.write_text("not sqlite", encoding="utf-8")
        _refresh_manifest_for_database(non_sqlite_backup.backup_path)
        non_sqlite_result = service.validate_backup(non_sqlite_backup.backup_id)
        self.assertFalse(non_sqlite_result.valid)
        self.assertFalse(non_sqlite_result.sqlite_integrity_valid)

        missing_migration_backup = service.create_backup()
        with closing(sqlite3.connect(missing_migration_backup.database_path)) as connection:
            connection.execute("DROP TABLE schema_migrations")
            connection.commit()
        _refresh_manifest_for_database(missing_migration_backup.backup_path)
        missing_migration_result = service.validate_backup(missing_migration_backup.backup_id)
        self.assertFalse(missing_migration_result.valid)
        self.assertIn("Database migration table was not found.", missing_migration_result.issues)

        foreign_key_backup = service.create_backup()
        with closing(sqlite3.connect(foreign_key_backup.database_path)) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                """
                INSERT INTO course_enrolments (
                    student_id,
                    course_id,
                    enrolment_date
                )
                VALUES (?, ?, ?)
                """,
                (99999, 99999, "2026-09-01"),
            )
            connection.commit()
        _refresh_manifest_for_database(foreign_key_backup.backup_path)
        foreign_key_result = service.validate_backup(foreign_key_backup.backup_id)
        self.assertFalse(foreign_key_result.valid)
        self.assertFalse(foreign_key_result.foreign_keys_valid)

    def test_manifest_tampering_cannot_override_database_schema(self):
        service = self._service()
        backup = service.create_backup()
        manifest = _read_manifest(backup.backup_path)
        manifest["schema_version"] = 0
        _write_manifest(backup.backup_path, manifest)

        result = service.validate_backup(backup.backup_id)

        self.assertFalse(result.valid)
        self.assertEqual(LATEST_SCHEMA_VERSION, result.schema_version)
        self.assertIn(
            "Backup manifest schema version does not match the database.",
            result.issues,
        )

    def test_newer_schema_backup_is_rejected_before_restore(self):
        service = self._service()
        backup = service.create_backup()
        with closing(sqlite3.connect(backup.database_path)) as connection:
            connection.execute(
                """
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (LATEST_SCHEMA_VERSION + 2, "future_schema", "2026-09-01T12:00:00Z"),
            )
            connection.commit()
        _refresh_manifest_for_database(
            backup.backup_path,
            schema_version=LATEST_SCHEMA_VERSION + 2,
            migration_versions=[1, LATEST_SCHEMA_VERSION + 2],
        )
        before = _database_state(self.config.paths.database_path)

        result = service.validate_backup(backup.backup_id)
        with self.assertRaises(BackupValidationError):
            service.restore_backup(backup.backup_id)

        self.assertFalse(result.schema_compatible)
        self.assertEqual(before, _database_state(self.config.paths.database_path))

    def test_restore_preserves_ids_relationships_history_decimals_and_migrations(self):
        service = self._service()
        self._seed_decimal_state()
        state_a = _database_state(self.config.paths.database_path)
        ids_a = _stable_ids(self.config.paths.database_path)
        decimals_a = _decimal_text_values(self.config.paths.database_path)

        backup = service.create_backup()
        self._mutate_to_state_b()
        self.assertNotEqual(state_a, _database_state(self.config.paths.database_path))

        result = service.restore_backup(backup.backup_id)

        self.assertEqual("Restore completed successfully.", result.message)
        self.assertEqual(LATEST_SCHEMA_VERSION, result.restored_schema_version)
        self.assertIsNotNone(result.safety_backup_id)
        self.assertEqual(state_a, _database_state(self.config.paths.database_path))
        self.assertEqual(ids_a, _stable_ids(self.config.paths.database_path))
        self.assertEqual(decimals_a, _decimal_text_values(self.config.paths.database_path))
        self.assertEqual((1,), _migration_history(self.config.paths.database_path))
        self.assertEqual("inactive", _student_status(self.config.paths.database_path, "STU-1005"))
        self.assertEqual("archived", _module_status(self.config.paths.database_path, "MOD-101"))
        self.assertEqual("cancelled", _enrolment_status(self.config.paths.database_path, "STU-1005"))
        self.assertEqual("ended", _assignment_status(self.config.paths.database_path, "TRN-1002"))
        self.assertEqual("archived", _assessment_status(self.config.paths.database_path, "Variables Practical"))
        self.assertEqual("ok", _integrity_check(self.config.paths.database_path))

    def test_pre_restore_safety_backup_contains_state_b(self):
        service = self._service()
        self._seed_decimal_state()
        backup_a = service.create_backup()
        self._mutate_to_state_b()
        state_b = _database_state(self.config.paths.database_path)

        result = service.restore_backup(backup_a.backup_id)

        safety_backup = service.inspect_backup(result.safety_backup_id)
        safety_manifest = _read_manifest(safety_backup.backup_path)
        self.assertEqual(BACKUP_REASON_PRE_RESTORE, safety_manifest["reason"])
        self.assertEqual(state_b, _database_state(safety_backup.database_path))

    def test_invalid_restore_leaves_live_database_unchanged(self):
        service = self._service()
        self._seed_decimal_state()
        backup = service.create_backup()
        self._mutate_to_state_b()
        live_state = _database_state(self.config.paths.database_path)
        manifest = _read_manifest(backup.backup_path)
        manifest["database_sha256"] = "0" * 64
        _write_manifest(backup.backup_path, manifest)

        with self.assertRaises(BackupValidationError):
            service.restore_backup(backup.backup_id)

        self.assertEqual(live_state, _database_state(self.config.paths.database_path))
        safety_backups = [
            item
            for item in service.list_backups()
            if item.reason == BACKUP_REASON_PRE_RESTORE
        ]
        self.assertEqual([], safety_backups)

    def test_restore_replace_failure_leaves_live_database_and_cleans_temp_files(self):
        service = self._service()
        self._seed_decimal_state()
        backup = service.create_backup()
        self._mutate_to_state_b()
        live_state = _database_state(self.config.paths.database_path)

        def fail_replace(source_path, destination_path):
            raise OSError("forced replace failure")

        service._replace_file = fail_replace

        with self.assertRaisesRegex(RestoreError, "before replacing"):
            service.restore_backup(backup.backup_id)

        self.assertEqual(live_state, _database_state(self.config.paths.database_path))
        self.assertEqual((), tuple(self.config.paths.temp_dir.iterdir()))
        safety_backups = [
            item
            for item in service.list_backups()
            if item.reason == BACKUP_REASON_PRE_RESTORE
        ]
        self.assertEqual(1, len(safety_backups))

    def test_restore_rolls_back_when_post_restore_validation_fails(self):
        service = self._service()
        self._seed_decimal_state()
        backup = service.create_backup()
        self._mutate_to_state_b()
        live_state = _database_state(self.config.paths.database_path)
        calls = {"count": 0}
        original_validator = service._validate_restored_live_database

        def fail_after_replacement():
            calls["count"] += 1
            if calls["count"] == 1:
                raise RestoreError("forced post-restore failure")
            return original_validator()

        service._validate_restored_live_database = fail_after_replacement

        with self.assertRaisesRegex(RestoreError, "recovered automatically"):
            service.restore_backup(backup.backup_id)

        self.assertEqual(live_state, _database_state(self.config.paths.database_path))

    def test_path_safety_rejects_untrusted_backup_ids(self):
        service = self._service()
        backup = service.create_backup()
        outside = self.project_root.parent / f"backup_{backup.backup_id}"
        self.assertFalse(outside.exists())

        for unsafe_id in ("../outside", r"..\outside", str(outside), "C:outside"):
            with self.subTest(unsafe_id=unsafe_id):
                with self.assertRaises(ValidationError):
                    service.validate_backup(unsafe_id)

        self.assertTrue(backup.backup_path.is_relative_to(self.config.paths.backup_dir))

    def test_backup_and_restore_events_are_logged(self):
        logger = ListLogger()
        service = self._service(logger=logger)
        self._seed_decimal_state()
        backup = service.create_backup()
        self._mutate_to_state_b()

        service.restore_backup(backup.backup_id)
        manifest = _read_manifest(backup.backup_path)
        manifest["database_sha256"] = "0" * 64
        _write_manifest(backup.backup_path, manifest)
        with self.assertRaises(BackupValidationError):
            service.restore_backup(backup.backup_id)

        messages = [message for level, message in logger.messages]
        self.assertIn("Backup created", messages)
        self.assertIn("Restore started", messages)
        self.assertIn("Restore completed", messages)
        self.assertIn("Restore rejected because backup validation failed", messages)

    def test_config_snapshot_is_included_when_runtime_config_exists(self):
        config_payload = {
            "application": {"name": "ITCA Training Centre Management System"},
            "runtime": {"database_file": "itca_training_centre.sqlite3"},
        }
        self.config.paths.config_file.write_text(
            json.dumps(config_payload),
            encoding="utf-8",
        )
        service = self._service()

        backup = service.create_backup()
        manifest = _read_manifest(backup.backup_path)

        self.assertEqual(BACKUP_CONFIG_FILENAME, manifest["config_filename"])
        self.assertTrue((backup.backup_path / BACKUP_CONFIG_FILENAME).is_file())
        self.assertEqual(
            sha256_file(backup.backup_path / BACKUP_CONFIG_FILENAME),
            manifest["config_sha256"],
        )

    def _service(self, logger=None) -> BackupService:
        return BackupService.from_config(
            self.config,
            clock=self.clock,
            uuid_factory=self.uuid_factory,
            logger=logger,
        )

    def _seed_decimal_state(self):
        seed_reporting_data(self.config.paths.database_path)
        students = StudentService(self.config.paths.database_path)
        courses = CourseService(self.config.paths.database_path)
        modules = ModuleService(self.config.paths.database_path)
        enrolments = CourseEnrolmentService(self.config.paths.database_path)
        trainers = TrainerService(self.config.paths.database_path)
        assignments = TrainerAssignmentService(self.config.paths.database_path)
        assessments = AssessmentService(self.config.paths.database_path)

        students.register_student("STU-DEC1", "Decimal", "One")
        courses.create_course(
            "DEC301",
            "Decimal Snapshot",
            fee_amount="0.1",
            status="active",
        )
        courses.create_course(
            "OLD101",
            "Archived Course",
            fee_amount="99.99",
            status="active",
        )
        courses.deactivate_course("OLD101")
        modules.create_module("DEC301", "MOD-DEC", "Decimal Values", 1)
        enrolments.enrol_student("STU-DEC1", "DEC301", "2026-09-01")
        trainers.register_trainer("TRN-DEC1", "Precise", "Trainer")
        assignments.assign_trainer("TRN-DEC1", "DEC301", "2026-09-01")
        assessment = assessments.create_assessment(
            "DEC301",
            "Decimal Assessment",
            "practical",
            "99.99",
            module_code="MOD-DEC",
            pass_mark="1.25",
        )
        assessments.record_mark(assessment.assessment_id, "STU-DEC1", "75.50")

    def _mutate_to_state_b(self):
        StudentService(self.config.paths.database_path).register_student(
            "STU-B000",
            "State",
            "Bee",
        )
        CourseService(self.config.paths.database_path).create_course(
            "NEW999",
            "Temporary Course",
            fee_amount="123",
            status="active",
        )


def _read_manifest(backup_path: Path) -> dict[str, object]:
    with open(backup_path / BACKUP_MANIFEST_FILENAME, "r", encoding="utf-8") as file_object:
        return json.load(file_object)


def _write_manifest(backup_path: Path, manifest: dict[str, object]) -> None:
    with open(backup_path / BACKUP_MANIFEST_FILENAME, "w", encoding="utf-8") as file_object:
        json.dump(manifest, file_object, indent=2, sort_keys=True)
        file_object.write("\n")


def _refresh_manifest_for_database(
    backup_path: Path,
    schema_version: int | None = None,
    migration_versions: list[int] | None = None,
) -> None:
    database_path = backup_path / BACKUP_DATABASE_FILENAME
    manifest = _read_manifest(backup_path)
    manifest["database_size_bytes"] = database_path.stat().st_size
    manifest["database_sha256"] = sha256_file(database_path)
    if schema_version is not None:
        manifest["schema_version"] = schema_version
    if migration_versions is not None:
        manifest["migration_versions"] = migration_versions
    _write_manifest(backup_path, manifest)


def _database_state(database_path: Path) -> dict[str, tuple[tuple[object, ...], ...]]:
    state = {}
    with open_database(database_path) as connection:
        for table_name in ("schema_migrations",) + OPERATIONAL_TABLES:
            rows = connection.execute(f"SELECT * FROM {table_name} ORDER BY rowid").fetchall()
            state[table_name] = tuple(tuple(row) for row in rows)
    return state


def _stable_ids(database_path: Path) -> dict[str, int]:
    with open_database(database_path) as connection:
        return {
            "student": connection.execute(
                "SELECT student_id FROM students WHERE student_number = ?",
                ("STU-1001",),
            ).fetchone()["student_id"],
            "course": connection.execute(
                "SELECT course_id FROM courses WHERE course_code = ?",
                ("PYF101",),
            ).fetchone()["course_id"],
            "module": connection.execute(
                "SELECT module_id FROM modules WHERE module_code = ?",
                ("MOD-101",),
            ).fetchone()["module_id"],
            "assessment": connection.execute(
                "SELECT assessment_id FROM assessments WHERE assessment_name = ?",
                ("Variables Practical",),
            ).fetchone()["assessment_id"],
            "mark": connection.execute(
                """
                SELECT mark_id
                FROM marks
                WHERE assessment_id = ?
                  AND student_id = ?
                """,
                (1, 1),
            ).fetchone()["mark_id"],
        }


def _decimal_text_values(database_path: Path) -> dict[str, str]:
    with open_database(database_path) as connection:
        return {
            "decimal_course_fee": connection.execute(
                "SELECT fee_amount FROM courses WHERE course_code = ?",
                ("DEC301",),
            ).fetchone()["fee_amount"],
            "archived_course_fee": connection.execute(
                "SELECT fee_amount FROM courses WHERE course_code = ?",
                ("OLD101",),
            ).fetchone()["fee_amount"],
            "assessment_max": connection.execute(
                "SELECT max_mark FROM assessments WHERE assessment_name = ?",
                ("Decimal Assessment",),
            ).fetchone()["max_mark"],
            "assessment_pass": connection.execute(
                "SELECT pass_mark FROM assessments WHERE assessment_name = ?",
                ("Decimal Assessment",),
            ).fetchone()["pass_mark"],
            "mark_obtained": connection.execute(
                """
                SELECT mark_obtained
                FROM marks
                JOIN assessments USING (assessment_id)
                WHERE assessment_name = ?
                """,
                ("Decimal Assessment",),
            ).fetchone()["mark_obtained"],
        }


def _migration_history(database_path: Path) -> tuple[int, ...]:
    with open_database(database_path) as connection:
        rows = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        return tuple(row["version"] for row in rows)


def _student_status(database_path: Path, student_number: str) -> str:
    with open_database(database_path) as connection:
        return connection.execute(
            "SELECT status FROM students WHERE student_number = ?",
            (student_number,),
        ).fetchone()["status"]


def _module_status(database_path: Path, module_code: str) -> str:
    with open_database(database_path) as connection:
        return connection.execute(
            "SELECT status FROM modules WHERE module_code = ?",
            (module_code,),
        ).fetchone()["status"]


def _enrolment_status(database_path: Path, student_number: str) -> str:
    with open_database(database_path) as connection:
        return connection.execute(
            """
            SELECT ce.status
            FROM course_enrolments ce
            JOIN students s ON s.student_id = ce.student_id
            WHERE s.student_number = ?
            ORDER BY ce.enrolment_id DESC
            """,
            (student_number,),
        ).fetchone()["status"]


def _assignment_status(database_path: Path, trainer_number: str) -> str:
    with open_database(database_path) as connection:
        return connection.execute(
            """
            SELECT ta.status
            FROM trainer_assignments ta
            JOIN trainers t ON t.trainer_id = ta.trainer_id
            WHERE t.trainer_number = ?
            ORDER BY ta.assignment_id DESC
            """,
            (trainer_number,),
        ).fetchone()["status"]


def _assessment_status(database_path: Path, assessment_name: str) -> str:
    with open_database(database_path) as connection:
        return connection.execute(
            "SELECT status FROM assessments WHERE assessment_name = ?",
            (assessment_name,),
        ).fetchone()["status"]


def _integrity_check(database_path: Path) -> str:
    with open_database(database_path) as connection:
        return connection.execute("PRAGMA integrity_check").fetchone()[0]


if __name__ == "__main__":
    unittest.main()
