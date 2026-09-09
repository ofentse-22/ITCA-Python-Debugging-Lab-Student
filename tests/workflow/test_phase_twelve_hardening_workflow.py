"""Adversarial workflow tests for Phase 12 hardening."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import unittest

from itca_training_centre.app import main
from itca_training_centre.config.settings import ensure_runtime_directories, load_config
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.import_export import IMPORT_STUDENTS
from itca_training_centre.services.assessment_service import (
    AssessmentService,
    round_percentage_for_display,
)
from itca_training_centre.services.attendance_service import AttendanceService
from itca_training_centre.services.backup_service import BackupService
from itca_training_centre.services.course_enrolment_service import CourseEnrolmentService
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.import_export_service import (
    IMPORT_SCHEMAS,
    EXPORT_STUDENTS,
    ImportExportService,
)
from itca_training_centre.services.module_service import ModuleService
from itca_training_centre.services.report_service import ReportService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.services.trainer_assignment_service import (
    TrainerAssignmentService,
)
from itca_training_centre.services.trainer_service import TrainerService
from itca_training_centre.utils.exceptions import RecordNotFoundError, ValidationError
from tests.reporting_helpers import operational_table_counts


class _SequenceClock:
    def __init__(self):
        self.current = datetime(2026, 9, 1, 14, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


class _SequenceUuidFactory:
    def __init__(self):
        self.values = ("12121212", "34343434", "56565656")
        self.index = 0

    def __call__(self):
        value = self.values[self.index]
        self.index += 1
        return value


class PhaseTwelveHardeningWorkflowTests(unittest.TestCase):
    def test_adversarial_temporary_environment_preserves_data_safety(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config = load_config(project_root=project_root)
            ensure_runtime_directories(config)
            initialize_database(config.paths.database_path)

            students = StudentService(config.paths.database_path)
            courses = CourseService(config.paths.database_path)
            modules = ModuleService(config.paths.database_path)
            enrolments = CourseEnrolmentService(config.paths.database_path)
            trainers = TrainerService(config.paths.database_path)
            assignments = TrainerAssignmentService(config.paths.database_path)
            attendance = AttendanceService(config.paths.database_path)
            assessments = AssessmentService(config.paths.database_path)
            reports = ReportService(config.paths.database_path)
            imports = ImportExportService(
                config.paths.database_path,
                config.paths.import_dir,
                config.paths.export_dir,
                clock=lambda: datetime(2026, 9, 1, 14, 30, 0),
            )
            backups = BackupService.from_config(
                config,
                clock=_SequenceClock(),
                uuid_factory=_SequenceUuidFactory(),
            )

            student_rows = (
                ("STU-1201", "Zoë", "O'Neil-Smith"),
                ("STU-1202", "Amina", "Nkosi"),
                ("STU-1203", "Bongi", "Mokoena"),
                ("STU-1204", "Celia", "Zulu"),
                ("STU-1205", "Dineo", "Abrahams"),
                ("STU-1206", "Unenrolled", "Learner"),
            )
            for student_number, first_name, last_name in student_rows:
                students.register_student(student_number, first_name, last_name)

            courses.create_course("PYH201", "Python Hardening", fee_amount="0.01", status="active")
            courses.create_course("SQL201", "SQLite Safety", fee_amount="1.25", status="active")
            modules.create_module("PYH201", "PY-M1", "Boundaries", "1")
            modules.create_module("SQL201", "SQL-M1", "Queries", "1")
            trainers.register_trainer("TRN-1201", "Naledi", "Dube")
            assignments.assign_trainer("TRN-1201", "PYH201", "2028-02-28")

            for student_number in ("STU-1201", "STU-1202", "STU-1203", "STU-1204", "STU-1205"):
                enrolments.enrol_student(student_number, "PYH201", "2028-02-28")

            with self.assertRaises(RecordNotFoundError):
                assessments.create_assessment(
                    "PYH201",
                    "Wrong Course Module",
                    "quiz",
                    "10",
                    module_code="SQL-M1",
                )

            session = attendance.create_session("PYH201", "2028-02-29", "Leap day, quotes \"ok\"")
            for student_number, status in (
                ("STU-1201", "present"),
                ("STU-1202", "late"),
                ("STU-1203", "absent"),
                ("STU-1204", "excused"),
                ("STU-1205", "unknown"),
            ):
                attendance.record_attendance(
                    session.session_id,
                    student_number,
                    status,
                    notes="checked, quoted, and backslash \\ value",
                )
            with self.assertRaises(ValidationError):
                attendance.record_attendance(session.session_id, "STU-1206", "present")

            attendance_report = reports.get_course_attendance_report(
                "PYH201",
                date_from="2028-02-29",
                date_to="2028-02-29",
            )
            low_attendance = reports.get_low_attendance_students("PYH201", "67")

            self.assertEqual(5, attendance_report.summary.record_count)
            self.assertEqual(3, attendance_report.summary.percentage_denominator)
            self.assertEqual(66.67, attendance_report.summary.attendance_percentage)
            self.assertEqual(
                ["STU-1203"],
                [row.student.student_number for row in low_attendance.students_below_threshold],
            )
            self.assertEqual(
                ["STU-1205", "STU-1204"],
                [
                    row.student.student_number
                    for row in low_attendance.students_without_calculable_attendance
                ],
            )

            assessment = assessments.create_assessment(
                "PYH201",
                "Hardening Practical",
                "practical",
                "10",
                module_code="PY-M1",
                pass_mark="5",
            )
            assessments.record_mark(assessment.assessment_id, "STU-1201", "0")
            assessments.record_mark(assessment.assessment_id, "STU-1202", "7.5")
            assessments.record_mark(assessment.assessment_id, "STU-1203", "10")
            assessments.record_mark(assessment.assessment_id, "STU-1204", "6")
            assessments.correct_mark(assessment.assessment_id, "STU-1204", "6.25")

            performance = reports.get_assessment_performance(assessment.assessment_id)
            performance_rows = {
                row.student.student_number: row
                for row in performance.students
            }

            self.assertEqual(5, performance.summary.expected_result_count)
            self.assertEqual(4, performance.summary.recorded_result_count)
            self.assertEqual(1, performance.summary.missing_result_count)
            self.assertEqual(3, performance.summary.pass_count)
            self.assertEqual(1, performance.summary.fail_count)
            self.assertEqual(Decimal("0"), performance_rows["STU-1201"].mark_obtained)
            self.assertEqual(Decimal("6.25"), performance_rows["STU-1204"].mark_obtained)
            self.assertTrue(performance_rows["STU-1205"].is_missing)
            self.assertEqual(
                Decimal("59.38"),
                round_percentage_for_display(performance.summary.average_percentage),
            )

            before_bad_preview = operational_table_counts(config.paths.database_path)
            _write_import_csv(
                config.paths.import_dir,
                "bad-students.csv",
                IMPORT_SCHEMAS[IMPORT_STUDENTS].headers,
                [
                    {
                        "student_number": "STU-1298",
                        "first_name": "",
                        "last_name": "Missing",
                        "email": "",
                        "phone": "",
                    }
                ],
            )
            bad_preview = imports.preview_import(IMPORT_STUDENTS, "bad-students.csv")

            self.assertFalse(bad_preview.is_importable)
            self.assertEqual(before_bad_preview, operational_table_counts(config.paths.database_path))

            _write_import_csv(
                config.paths.import_dir,
                "valid-students.csv",
                IMPORT_SCHEMAS[IMPORT_STUDENTS].headers,
                [
                    {
                        "student_number": "STU-1299",
                        "first_name": "Imported",
                        "last_name": "Learner",
                        "email": "",
                        "phone": "",
                    }
                ],
            )
            import_result = imports.commit_import(
                imports.preview_import(IMPORT_STUDENTS, "valid-students.csv")
            )
            export_result = imports.export_operational_data(EXPORT_STUDENTS)
            state_before_backup = operational_table_counts(config.paths.database_path)
            backup = backups.create_backup("phase 12 hardening")

            students.register_student("STU-MUT", "Temporary", "Mutation")
            self.assertNotEqual(
                state_before_backup,
                operational_table_counts(config.paths.database_path),
            )

            backups.restore_backup(backup.backup_id)

            self.assertEqual(1, import_result.created_count)
            self.assertTrue(export_result.output_path.is_relative_to(config.paths.export_dir))
            self.assertEqual(state_before_backup, operational_table_counts(config.paths.database_path))
            restored_performance = reports.get_assessment_performance(assessment.assessment_id)
            restored_rows = {
                row.student.student_number: row
                for row in restored_performance.students
            }
            self.assertEqual(Decimal("0"), restored_rows["STU-1201"].mark_obtained)
            self.assertEqual(Decimal("6.25"), restored_rows["STU-1204"].mark_obtained)

    def test_repeated_cli_navigation_invalid_choices_and_clean_exit(self):
        choices = iter(["x", ""] + ["1", "0"] * 20 + ["0"])

        with TemporaryDirectory() as temp_dir:
            output = []
            exit_code = main(
                input_func=lambda prompt: next(choices),
                output_func=output.append,
                project_root=Path(temp_dir),
            )

        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(output.count("Student Management"), 20)
        self.assertIn("Choose a number from the menu.", output)
        self.assertIn("Application exited cleanly.", output)


def _write_import_csv(
    import_dir: Path,
    filename: str,
    headers: tuple[str, ...],
    rows: list[dict[str, object]],
) -> Path:
    path = import_dir / filename
    with open(path, "w", encoding="utf-8", newline="") as file_object:
        writer = csv.DictWriter(file_object, fieldnames=list(headers))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


if __name__ == "__main__":
    unittest.main()
