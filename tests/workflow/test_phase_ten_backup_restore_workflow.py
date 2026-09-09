"""End-to-end workflow test for Phase 10 backup and restore behavior."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.config.settings import ensure_runtime_directories, load_config
from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.data.schema import LATEST_SCHEMA_VERSION
from itca_training_centre.models.import_export import (
    EXPORT_MARKS,
    EXPORT_STUDENTS,
    REPORT_SYSTEM_OVERVIEW,
)
from itca_training_centre.services.assessment_service import AssessmentService
from itca_training_centre.services.backup_service import BackupService
from itca_training_centre.services.course_enrolment_service import CourseEnrolmentService
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.import_export_service import ImportExportService
from itca_training_centre.services.module_service import ModuleService
from itca_training_centre.services.report_service import ReportService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.storage.backup_storage import sha256_file
from tests.reporting_helpers import OPERATIONAL_TABLES, seed_reporting_data


class SequenceClock:
    """Deterministic UTC clock for the Phase 10 workflow."""

    def __init__(self):
        self.current = datetime(2026, 9, 1, 15, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


class SequenceUuidFactory:
    """Deterministic UUID suffix provider for the Phase 10 workflow."""

    def __init__(self):
        self.values = ("aaaaaaaa", "bbbbbbbb", "cccccccc")
        self.index = 0

    def __call__(self):
        value = self.values[self.index]
        self.index += 1
        return value


class PhaseTenBackupRestoreWorkflowTests(unittest.TestCase):
    def test_phase_ten_backup_restore_end_to_end(self):
        with TemporaryDirectory() as temp_dir:
            config = load_config(project_root=Path(temp_dir))
            ensure_runtime_directories(config)
            initialize_database(config.paths.database_path)
            self._seed_representative_data(config.paths.database_path)

            backup_service = BackupService.from_config(
                config,
                clock=SequenceClock(),
                uuid_factory=SequenceUuidFactory(),
            )
            export_service = ImportExportService(
                database_path=config.paths.database_path,
                import_dir=config.paths.import_dir,
                export_dir=config.paths.export_dir,
                clock=lambda: datetime(2026, 9, 1, 15, 30, 0),
            )
            reports = ReportService(config.paths.database_path)

            report_a = reports.get_system_overview()
            state_a = _database_state(config.paths.database_path)
            ids_a = _stable_ids(config.paths.database_path)
            decimals_a = _decimal_text_values(config.paths.database_path)

            backup_a = backup_service.create_backup(reason="phase 10 e2e")
            backup_a_sha = sha256_file(backup_a.database_path)
            self.assertTrue(backup_service.validate_backup(backup_a.backup_id).valid)

            student_export = export_service.export_operational_data(EXPORT_STUDENTS)
            mark_export = export_service.export_operational_data(EXPORT_MARKS)
            overview_export = export_service.export_report(REPORT_SYSTEM_OVERVIEW)
            recent_export_names = {
                export.filename for export in export_service.list_recent_exports()
            }
            self.assertIn(student_export.output_path.name, recent_export_names)
            self.assertIn(mark_export.output_path.name, recent_export_names)
            self.assertIn(overview_export.output_path.name, recent_export_names)
            self.assertNotIn(backup_a.backup_path.name, recent_export_names)

            self._mutate_live_database(config.paths.database_path)
            state_b = _database_state(config.paths.database_path)
            report_b = ReportService(config.paths.database_path).get_system_overview()
            self.assertGreater(report_b.student_count, report_a.student_count)
            self.assertGreater(report_b.course_count, report_a.course_count)
            self.assertNotEqual(state_a, state_b)

            restore_result = backup_service.restore_backup(backup_a.backup_id)
            safety_backup = backup_service.inspect_backup(restore_result.safety_backup_id)
            second_backup = backup_service.create_backup(reason="after restore")

            report_restored = ReportService(config.paths.database_path).get_system_overview()
            backup_list = backup_service.list_backups()

            self.assertEqual("Restore completed successfully.", restore_result.message)
            self.assertEqual(LATEST_SCHEMA_VERSION, restore_result.restored_schema_version)
            self.assertEqual(state_a, _database_state(config.paths.database_path))
            self.assertEqual(state_b, _database_state(safety_backup.database_path))
            self.assertEqual(ids_a, _stable_ids(config.paths.database_path))
            self.assertEqual(decimals_a, _decimal_text_values(config.paths.database_path))
            self.assertEqual(report_a.student_count, report_restored.student_count)
            self.assertEqual(report_a.mark_count, report_restored.mark_count)
            self.assertEqual((1,), _migration_history(config.paths.database_path))
            self.assertEqual("ok", _integrity_check(config.paths.database_path))
            self.assertEqual(backup_a_sha, sha256_file(backup_a.database_path))
            self.assertEqual(
                [second_backup.backup_id, safety_backup.backup_id, backup_a.backup_id],
                [backup.backup_id for backup in backup_list],
            )
            self.assertTrue(student_export.output_path.exists())
            self.assertTrue(mark_export.output_path.exists())
            self.assertTrue(overview_export.output_path.exists())

    def _seed_representative_data(self, database_path: Path) -> None:
        seed_reporting_data(database_path)
        students = StudentService(database_path)
        courses = CourseService(database_path)
        modules = ModuleService(database_path)
        enrolments = CourseEnrolmentService(database_path)
        assessments = AssessmentService(database_path)

        students.register_student("STU-D010", "Decimal", "Learner")
        courses.create_course(
            "DEC401",
            "Decimal Recovery",
            fee_amount="0.1",
            status="active",
        )
        modules.create_module("DEC401", "MOD-DEC", "Decimal Storage", 1)
        enrolments.enrol_student("STU-D010", "DEC401", "2026-09-01")
        assessment = assessments.create_assessment(
            "DEC401",
            "Decimal Recovery Practical",
            "practical",
            "99.99",
            module_code="MOD-DEC",
            pass_mark="1.25",
        )
        assessments.record_mark(assessment.assessment_id, "STU-D010", "75.50")

    def _mutate_live_database(self, database_path: Path) -> None:
        StudentService(database_path).register_student("STU-LIVE", "Live", "Mutation")
        CourseService(database_path).create_course(
            "TMP401",
            "Temporary Live Course",
            fee_amount="25",
            status="active",
        )


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
                ("STU-D010",),
            ).fetchone()["student_id"],
            "course": connection.execute(
                "SELECT course_id FROM courses WHERE course_code = ?",
                ("DEC401",),
            ).fetchone()["course_id"],
            "module": connection.execute(
                "SELECT module_id FROM modules WHERE module_code = ?",
                ("MOD-DEC",),
            ).fetchone()["module_id"],
            "assessment": connection.execute(
                "SELECT assessment_id FROM assessments WHERE assessment_name = ?",
                ("Decimal Recovery Practical",),
            ).fetchone()["assessment_id"],
        }


def _decimal_text_values(database_path: Path) -> dict[str, str]:
    with open_database(database_path) as connection:
        return {
            "course_fee": connection.execute(
                "SELECT fee_amount FROM courses WHERE course_code = ?",
                ("DEC401",),
            ).fetchone()["fee_amount"],
            "assessment_max": connection.execute(
                "SELECT max_mark FROM assessments WHERE assessment_name = ?",
                ("Decimal Recovery Practical",),
            ).fetchone()["max_mark"],
            "assessment_pass": connection.execute(
                "SELECT pass_mark FROM assessments WHERE assessment_name = ?",
                ("Decimal Recovery Practical",),
            ).fetchone()["pass_mark"],
            "mark_obtained": connection.execute(
                """
                SELECT mark_obtained
                FROM marks
                JOIN assessments USING (assessment_id)
                WHERE assessment_name = ?
                """,
                ("Decimal Recovery Practical",),
            ).fetchone()["mark_obtained"],
            "zero_mark": connection.execute(
                "SELECT mark_obtained FROM marks WHERE mark_id = ?",
                (1,),
            ).fetchone()["mark_obtained"],
        }


def _migration_history(database_path: Path) -> tuple[int, ...]:
    with open_database(database_path) as connection:
        rows = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        return tuple(row["version"] for row in rows)


def _integrity_check(database_path: Path) -> str:
    with open_database(database_path) as connection:
        return connection.execute("PRAGMA integrity_check").fetchone()[0]


if __name__ == "__main__":
    unittest.main()
