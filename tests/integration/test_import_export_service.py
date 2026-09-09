"""Integration tests for ImportExportService."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import os
import unittest

from itca_training_centre.config.settings import ensure_runtime_directories, load_config
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.import_export import (
    EXPORT_ASSESSMENTS,
    EXPORT_ATTENDANCE,
    EXPORT_COURSES,
    EXPORT_ENROLMENTS,
    EXPORT_MARKS,
    EXPORT_MODULES,
    EXPORT_STUDENTS,
    EXPORT_TRAINER_ASSIGNMENTS,
    EXPORT_TRAINERS,
    IMPORT_COURSES,
    IMPORT_ENROLMENTS,
    IMPORT_MODULES,
    IMPORT_STUDENTS,
    IMPORT_TRAINERS,
    REPORT_ASSESSMENT_PERFORMANCE,
    REPORT_LOW_ATTENDANCE,
    REPORT_STUDENT_PROGRESS,
    REPORT_SYSTEM_OVERVIEW,
)
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.import_export_service import (
    IMPORT_SCHEMAS,
    OPERATIONAL_EXPORT_SCHEMAS,
    ImportExportService,
)
from itca_training_centre.services.report_service import ReportService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    ImportValidationError,
    RecordNotFoundError,
)
from tests.reporting_helpers import operational_table_counts, seed_reporting_data


class ImportExportServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = TemporaryDirectory()
        self.project_root = Path(self.temp_context.__enter__())
        self.config = load_config(project_root=self.project_root)
        ensure_runtime_directories(self.config)
        initialize_database(self.config.paths.database_path)
        self.service = ImportExportService(
            database_path=self.config.paths.database_path,
            import_dir=self.config.paths.import_dir,
            export_dir=self.config.paths.export_dir,
            clock=lambda: datetime(2026, 9, 1, 10, 30, 0),
        )

    def tearDown(self):
        self.temp_context.__exit__(None, None, None)

    def test_student_import_preview_is_read_only_and_commit_creates_records(self):
        source_path = self._write_import_csv(
            "students.csv",
            IMPORT_SCHEMAS[IMPORT_STUDENTS].headers,
            [
                {
                    "student_number": "stu-2001",
                    "first_name": "Ama,hle",
                    "last_name": "Nkosi",
                    "email": "AMAHLE@EXAMPLE.EDU",
                    "phone": "+27 11 555 0101",
                },
                {
                    "student_number": "STU-2002",
                    "first_name": "Zoë",
                    "last_name": "Maseko",
                    "email": "",
                    "phone": "",
                },
            ],
        )
        before_file = source_path.read_text(encoding="utf-8")
        before_counts = operational_table_counts(self.config.paths.database_path)

        preview = self.service.preview_import(IMPORT_STUDENTS, "students.csv")

        self.assertTrue(preview.is_importable)
        self.assertEqual(2, preview.total_rows)
        self.assertEqual(2, preview.valid_row_count)
        self.assertEqual(before_counts, operational_table_counts(self.config.paths.database_path))

        result = self.service.commit_import(preview)

        students = StudentService(self.config.paths.database_path).list_students()
        self.assertEqual(2, result.created_count)
        self.assertEqual(["STU-2002", "STU-2001"], [student.student_number for student in students])
        self.assertEqual("amahle@example.edu", students[1].email)
        self.assertEqual(before_file, source_path.read_text(encoding="utf-8"))

    def test_student_import_reports_file_and_row_validation_problems(self):
        self._write_import_csv(
            "missing-header.csv",
            ("student_number", "first_name"),
            [],
        )
        self._write_import_csv(
            "bad-row.csv",
            IMPORT_SCHEMAS[IMPORT_STUDENTS].headers,
            [
                {
                    "student_number": "STU-3001",
                    "first_name": "",
                    "last_name": "Nkosi",
                    "email": "not-an-email",
                    "phone": "",
                }
            ],
        )

        header_preview = self.service.preview_import(
            IMPORT_STUDENTS,
            "missing-header.csv",
        )
        row_preview = self.service.preview_import(IMPORT_STUDENTS, "bad-row.csv")

        self.assertTrue(header_preview.has_fatal_error)
        self.assertIn("missing required headers", header_preview.fatal_error)
        self.assertFalse(row_preview.is_importable)
        self.assertEqual(1, row_preview.invalid_row_count)
        self.assertEqual(["first_name", "email"], [issue.field_name for issue in row_preview.issues])
        with self.assertRaises(ImportValidationError):
            self.service.commit_import(row_preview)

    def test_duplicate_conflicts_block_create_only_student_import(self):
        StudentService(self.config.paths.database_path).register_student(
            "STU-4001",
            "Existing",
            "Student",
            email="existing@example.edu",
        )
        self._write_import_csv(
            "conflicts.csv",
            IMPORT_SCHEMAS[IMPORT_STUDENTS].headers,
            [
                {
                    "student_number": "STU-4001",
                    "first_name": "Again",
                    "last_name": "Student",
                    "email": "",
                    "phone": "",
                },
                {
                    "student_number": "STU-4002",
                    "first_name": "New",
                    "last_name": "Student",
                    "email": "existing@example.edu",
                    "phone": "",
                },
                {
                    "student_number": "STU-4003",
                    "first_name": "File",
                    "last_name": "Duplicate",
                    "email": "dup@example.edu",
                    "phone": "",
                },
                {
                    "student_number": "STU-4004",
                    "first_name": "File",
                    "last_name": "Duplicate",
                    "email": "dup@example.edu",
                    "phone": "",
                },
            ],
        )

        preview = self.service.preview_import(IMPORT_STUDENTS, "conflicts.csv")

        self.assertFalse(preview.is_importable)
        self.assertEqual(3, preview.conflict_count)
        self.assertEqual(1, preview.valid_row_count)
        with self.assertRaises(ImportValidationError):
            self.service.commit_import(preview)

    def test_course_module_trainer_and_enrolment_imports_use_domain_rules(self):
        student_service = StudentService(self.config.paths.database_path)
        student_service.register_student("STU-5001", "Naledi", "Mokoena")
        self._write_import_csv(
            "courses.csv",
            IMPORT_SCHEMAS[IMPORT_COURSES].headers,
            [
                {
                    "course_code": "pyf101",
                    "course_name": "Python Fundamentals",
                    "description": "Variables, strings, and loops",
                    "fee_amount": "75.50",
                    "status": "active",
                },
                {
                    "course_code": "DEC101",
                    "course_name": "Decimal Practice",
                    "description": "",
                    "fee_amount": "0.1",
                    "status": "planned",
                },
            ],
        )
        self._write_import_csv(
            "modules.csv",
            IMPORT_SCHEMAS[IMPORT_MODULES].headers,
            [
                {
                    "course_code": "PYF101",
                    "module_code": "mod-001",
                    "module_name": "Variables",
                    "sequence_number": "1",
                    "status": "active",
                }
            ],
        )
        self._write_import_csv(
            "trainers.csv",
            IMPORT_SCHEMAS[IMPORT_TRAINERS].headers,
            [
                {
                    "trainer_number": "trn-5001",
                    "first_name": "Thandi",
                    "last_name": "Dlamini",
                    "email": "",
                    "phone": "",
                }
            ],
        )
        self._write_import_csv(
            "enrolments.csv",
            IMPORT_SCHEMAS[IMPORT_ENROLMENTS].headers,
            [
                {
                    "student_number": "STU-5001",
                    "course_code": "PYF101",
                    "enrolment_date": "2026-09-01",
                }
            ],
        )

        self.service.commit_import(self.service.preview_import(IMPORT_COURSES, "courses.csv"))
        self.service.commit_import(self.service.preview_import(IMPORT_MODULES, "modules.csv"))
        self.service.commit_import(self.service.preview_import(IMPORT_TRAINERS, "trainers.csv"))
        enrolment_preview = self.service.preview_import(IMPORT_ENROLMENTS, "enrolments.csv")
        self.assertTrue(enrolment_preview.is_importable)
        self.service.commit_import(enrolment_preview)

        exported_courses = self.service.export_operational_data(EXPORT_COURSES)
        rows = self._read_export_csv(exported_courses.output_path)

        self.assertEqual("75.5", rows[1]["fee_amount"])
        self.assertEqual("0.1", rows[0]["fee_amount"])
        self.assertEqual(1, operational_table_counts(self.config.paths.database_path)["modules"])
        self.assertEqual(1, operational_table_counts(self.config.paths.database_path)["trainers"])
        self.assertEqual(1, operational_table_counts(self.config.paths.database_path)["course_enrolments"])

    def test_module_and_enrolment_imports_report_relationship_problems(self):
        course_service = CourseService(self.config.paths.database_path)
        student_service = StudentService(self.config.paths.database_path)
        course_service.create_course("PLAN101", "Planned Course", fee_amount="1.25")
        student_service.register_student("STU-6001", "Inactive", "Student")
        student_service.deactivate_student("STU-6001")
        self._write_import_csv(
            "bad-modules.csv",
            IMPORT_SCHEMAS[IMPORT_MODULES].headers,
            [
                {
                    "course_code": "MISSING",
                    "module_code": "MOD-001",
                    "module_name": "Missing Course",
                    "sequence_number": "1",
                    "status": "active",
                },
                {
                    "course_code": "PLAN101",
                    "module_code": "MOD-002",
                    "module_name": "Bad Sequence",
                    "sequence_number": "0",
                    "status": "active",
                },
            ],
        )
        self._write_import_csv(
            "bad-enrolments.csv",
            IMPORT_SCHEMAS[IMPORT_ENROLMENTS].headers,
            [
                {
                    "student_number": "STU-6001",
                    "course_code": "PLAN101",
                    "enrolment_date": "2026-09-01",
                },
                {
                    "student_number": "MISSING",
                    "course_code": "PLAN101",
                    "enrolment_date": "2026-09-01",
                },
            ],
        )

        module_preview = self.service.preview_import(IMPORT_MODULES, "bad-modules.csv")
        enrolment_preview = self.service.preview_import(IMPORT_ENROLMENTS, "bad-enrolments.csv")

        self.assertFalse(module_preview.is_importable)
        self.assertTrue(any(issue.field_name == "course_code" for issue in module_preview.issues))
        self.assertTrue(any(issue.field_name == "sequence_number" for issue in module_preview.issues))
        self.assertFalse(enrolment_preview.is_importable)
        self.assertTrue(any("Student must be active" in issue.message for issue in enrolment_preview.issues))
        self.assertTrue(any("Student number was not found" in issue.message for issue in enrolment_preview.issues))

    def test_confirmed_import_rolls_back_when_data_changes_after_preview(self):
        self._write_import_csv(
            "atomic.csv",
            IMPORT_SCHEMAS[IMPORT_STUDENTS].headers,
            [
                {
                    "student_number": "STU-7001",
                    "first_name": "First",
                    "last_name": "Student",
                    "email": "",
                    "phone": "",
                },
                {
                    "student_number": "STU-7002",
                    "first_name": "Second",
                    "last_name": "Student",
                    "email": "",
                    "phone": "",
                },
            ],
        )
        preview = self.service.preview_import(IMPORT_STUDENTS, "atomic.csv")
        self.assertTrue(preview.is_importable)
        StudentService(self.config.paths.database_path).register_student(
            "STU-7002",
            "Already",
            "There",
        )

        with self.assertRaises(DuplicateRecordError):
            self.service.commit_import(preview)

        students = StudentService(self.config.paths.database_path)
        with self.assertRaises(RecordNotFoundError):
            students.get_student_by_number("STU-7001")
        self.assertEqual("STU-7002", students.get_student_by_number("STU-7002").student_number)

    def test_import_path_safety_and_empty_file_handling(self):
        empty_file = self.config.paths.import_dir / "empty.csv"
        empty_file.write_text("", encoding="utf-8")
        text_file = self.config.paths.import_dir / "students.txt"
        text_file.write_text("student_number\nSTU-001\n", encoding="utf-8")
        directory = self.config.paths.import_dir / "directory.csv"
        directory.mkdir()

        traversal = self.service.preview_import(IMPORT_STUDENTS, "../students.csv")
        empty = self.service.preview_import(IMPORT_STUDENTS, "empty.csv")
        wrong_extension = self.service.preview_import(IMPORT_STUDENTS, "students.txt")
        directory_preview = self.service.preview_import(IMPORT_STUDENTS, "directory.csv")

        self.assertIn("outside the controlled directory", traversal.fatal_error)
        self.assertIn("empty", empty.fatal_error)
        self.assertIn(".csv", wrong_extension.fatal_error)
        self.assertIn("regular file", directory_preview.fatal_error)

    def test_operational_exports_are_read_only_controlled_and_business_keyed(self):
        seed_reporting_data(self.config.paths.database_path)
        StudentService(self.config.paths.database_path).register_student(
            "STU-FORM",
            "=Formula",
            "Safety",
            phone="@phone",
        )
        before_counts = operational_table_counts(self.config.paths.database_path)
        export_types = (
            EXPORT_STUDENTS,
            EXPORT_COURSES,
            EXPORT_MODULES,
            EXPORT_TRAINERS,
            EXPORT_ENROLMENTS,
            EXPORT_TRAINER_ASSIGNMENTS,
            EXPORT_ATTENDANCE,
            EXPORT_ASSESSMENTS,
            EXPORT_MARKS,
        )

        results = [self.service.export_operational_data(export_type) for export_type in export_types]

        self.assertEqual(before_counts, operational_table_counts(self.config.paths.database_path))
        self.assertEqual(
            len(export_types),
            len({result.output_path.name for result in results}),
        )
        for result in results:
            self.assertTrue(result.output_path.is_relative_to(self.config.paths.export_dir))
            self.assertTrue(result.output_path.exists())
            expected_headers = OPERATIONAL_EXPORT_SCHEMAS[result.export_type].headers
            self.assertEqual(expected_headers, tuple(self._read_export_csv(result.output_path)[0]))

        student_rows = self._read_export_csv(results[0].output_path)
        self.assertTrue(any(row["first_name"] == "'=Formula" for row in student_rows))
        self.assertTrue(any(row["phone"] == "'@phone" for row in student_rows))
        enrolment_headers = tuple(student_rows[0].keys())
        self.assertNotIn("student_id", enrolment_headers)

        mark_rows = self._read_export_csv(results[-1].output_path)
        self.assertTrue(any(row["mark_obtained"] == "0" for row in mark_rows))
        self.assertTrue(any(row["mark_obtained"] == "1.25" for row in mark_rows))

    def test_report_exports_match_report_service_values(self):
        fixture = seed_reporting_data(self.config.paths.database_path)
        report_service = ReportService(self.config.paths.database_path)

        system_result = self.service.export_report(REPORT_SYSTEM_OVERVIEW)
        student_result = self.service.export_report(
            REPORT_STUDENT_PROGRESS,
            student_number="STU-1001",
        )
        low_result = self.service.export_report(
            REPORT_LOW_ATTENDANCE,
            course_code="PYF101",
            threshold_percentage="100",
        )
        performance_result = self.service.export_report(
            REPORT_ASSESSMENT_PERFORMANCE,
            assessment_id=str(fixture.assessment_practical.assessment_id),
        )

        system_text = system_result.output_path.read_text(encoding="utf-8")
        student_text = student_result.output_path.read_text(encoding="utf-8")
        low_rows = self._read_export_csv(low_result.output_path)
        performance_rows = self._read_export_csv(performance_result.output_path)
        low_report = report_service.get_low_attendance_students("PYF101", "100")

        self.assertIn("Students", system_text)
        self.assertIn("6", system_text)
        self.assertIn("0/100", student_text)
        self.assertEqual(2, len(low_report.students_below_threshold))
        self.assertTrue(any(row["student_number"] == "STU-1001" for row in low_rows))
        self.assertTrue(any(row["student_number"] == "STU-1003" and row["attendance_percentage"] == "" for row in low_rows))
        self.assertTrue(any(row["student_number"] == "STU-1001" and row["mark_obtained"] == "0" for row in performance_rows))
        self.assertTrue(any(row["student_number"] == "STU-1003" and row["mark_obtained"] == "" for row in performance_rows))

    def test_recent_exports_lists_direct_files_only(self):
        seed_reporting_data(self.config.paths.database_path)
        first = self.service.export_operational_data(EXPORT_STUDENTS)
        second = self.service.export_operational_data(EXPORT_STUDENTS)
        nested = self.config.paths.export_dir / "nested"
        nested.mkdir()
        (nested / "ignored.csv").write_text("ignored", encoding="utf-8")

        recent = self.service.list_recent_exports()

        filenames = {file_info.filename for file_info in recent}
        self.assertIn(first.output_path.name, filenames)
        self.assertIn(second.output_path.name, filenames)
        self.assertNotIn("ignored.csv", filenames)
        self.assertNotEqual(first.output_path.name, second.output_path.name)

    def test_recent_exports_orders_equal_timestamps_by_filename(self):
        fixed_timestamp = datetime(2026, 9, 1, 12, 0, 0).timestamp()
        first = self.config.paths.export_dir / "b.csv"
        second = self.config.paths.export_dir / "a.csv"
        for path in (first, second):
            path.write_text("name\nvalue\n", encoding="utf-8")
            os.utime(path, (fixed_timestamp, fixed_timestamp))

        recent = self.service.list_recent_exports()

        self.assertEqual(["a.csv", "b.csv"], [item.filename for item in recent])

    def _write_import_csv(
        self,
        filename: str,
        headers: tuple[str, ...],
        rows: list[dict[str, object]],
    ) -> Path:
        path = self.config.paths.import_dir / filename
        with open(path, "w", encoding="utf-8", newline="") as file_object:
            writer = csv.DictWriter(file_object, fieldnames=list(headers))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path

    def _read_export_csv(self, path: Path) -> list[dict[str, str]]:
        with open(path, "r", encoding="utf-8", newline="") as file_object:
            return list(csv.DictReader(file_object))


if __name__ == "__main__":
    unittest.main()
