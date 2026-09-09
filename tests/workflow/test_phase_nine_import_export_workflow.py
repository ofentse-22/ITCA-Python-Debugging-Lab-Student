"""End-to-end workflow test for Phase 9 import/export behavior."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import unittest

from itca_training_centre.config.settings import ensure_runtime_directories, load_config
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.import_export import (
    EXPORT_COURSES,
    EXPORT_MARKS,
    EXPORT_STUDENTS,
    IMPORT_COURSES,
    IMPORT_ENROLMENTS,
    IMPORT_MODULES,
    IMPORT_STUDENTS,
    IMPORT_TRAINERS,
    REPORT_ASSESSMENT_PERFORMANCE,
    REPORT_LOW_ATTENDANCE,
    REPORT_SYSTEM_OVERVIEW,
)
from itca_training_centre.services.assessment_service import AssessmentService
from itca_training_centre.services.attendance_service import AttendanceService
from itca_training_centre.services.import_export_service import (
    IMPORT_SCHEMAS,
    ImportExportService,
)
from itca_training_centre.services.report_service import ReportService
from itca_training_centre.services.trainer_assignment_service import (
    TrainerAssignmentService,
)
from itca_training_centre.utils.exceptions import ImportValidationError
from tests.reporting_helpers import operational_table_counts


class PhaseNineImportExportWorkflowTests(unittest.TestCase):
    def test_phase_nine_import_export_end_to_end(self):
        with TemporaryDirectory() as temp_dir:
            config = load_config(project_root=Path(temp_dir))
            ensure_runtime_directories(config)
            initialize_database(config.paths.database_path)
            service = ImportExportService(
                database_path=config.paths.database_path,
                import_dir=config.paths.import_dir,
                export_dir=config.paths.export_dir,
                clock=lambda: datetime(2026, 9, 1, 14, 0, 0),
            )

            self._write_csv(
                config.paths.import_dir / "students.csv",
                IMPORT_SCHEMAS[IMPORT_STUDENTS].headers,
                [
                    {
                        "student_number": "stu-1001",
                        "first_name": "Lebo, Jr",
                        "last_name": "Mokoena",
                        "email": "lebo@example.edu",
                        "phone": "",
                    },
                    {
                        "student_number": "STU-1002",
                        "first_name": "Mia",
                        "last_name": "Zoë",
                        "email": "",
                        "phone": "+27 12 555 0002",
                    },
                ],
            )
            self._write_csv(
                config.paths.import_dir / "courses.csv",
                IMPORT_SCHEMAS[IMPORT_COURSES].headers,
                [
                    {
                        "course_code": "PYF201",
                        "course_name": "Python File Handling",
                        "description": "CSV and text files",
                        "fee_amount": "99.99",
                        "status": "active",
                    },
                    {
                        "course_code": "DEC201",
                        "course_name": "Decimal Accuracy",
                        "description": "",
                        "fee_amount": "1.25",
                        "status": "active",
                    },
                ],
            )
            self._write_csv(
                config.paths.import_dir / "modules.csv",
                IMPORT_SCHEMAS[IMPORT_MODULES].headers,
                [
                    {
                        "course_code": "PYF201",
                        "module_code": "MOD-CSV",
                        "module_name": "CSV Files",
                        "sequence_number": "1",
                        "status": "active",
                    }
                ],
            )
            self._write_csv(
                config.paths.import_dir / "trainers.csv",
                IMPORT_SCHEMAS[IMPORT_TRAINERS].headers,
                [
                    {
                        "trainer_number": "TRN-1001",
                        "first_name": "Nandi",
                        "last_name": "Khumalo",
                        "email": "",
                        "phone": "",
                    }
                ],
            )
            self._write_csv(
                config.paths.import_dir / "enrolments.csv",
                IMPORT_SCHEMAS[IMPORT_ENROLMENTS].headers,
                [
                    {
                        "student_number": "STU-1001",
                        "course_code": "PYF201",
                        "enrolment_date": "2026-09-01",
                    },
                    {
                        "student_number": "STU-1002",
                        "course_code": "PYF201",
                        "enrolment_date": "2026-09-01",
                    },
                ],
            )

            before_preview = operational_table_counts(config.paths.database_path)
            student_preview = service.preview_import(IMPORT_STUDENTS, "students.csv")
            self.assertTrue(student_preview.is_importable)
            self.assertEqual(before_preview, operational_table_counts(config.paths.database_path))

            for import_type, filename in (
                (IMPORT_STUDENTS, "students.csv"),
                (IMPORT_COURSES, "courses.csv"),
                (IMPORT_MODULES, "modules.csv"),
                (IMPORT_TRAINERS, "trainers.csv"),
                (IMPORT_ENROLMENTS, "enrolments.csv"),
            ):
                preview = (
                    student_preview
                    if import_type == IMPORT_STUDENTS
                    else service.preview_import(import_type, filename)
                )
                self.assertTrue(preview.is_importable)
                service.commit_import(preview)

            assignments = TrainerAssignmentService(config.paths.database_path)
            attendance = AttendanceService(config.paths.database_path)
            assessments = AssessmentService(config.paths.database_path)
            assignments.assign_trainer("TRN-1001", "PYF201", "2026-09-01")
            session = attendance.create_session("PYF201", "2026-09-02", "CSV Practice")
            attendance.record_attendance(session.session_id, "STU-1001", "present")
            attendance.record_attendance(session.session_id, "STU-1002", "absent")
            assessment = assessments.create_assessment(
                "PYF201",
                "CSV Practical",
                "practical",
                "100",
                module_code="MOD-CSV",
                pass_mark="50",
            )
            assessments.record_mark(assessment.assessment_id, "STU-1001", "0")
            assessments.record_mark(assessment.assessment_id, "STU-1002", "75.50")

            before_export = operational_table_counts(config.paths.database_path)
            student_export = service.export_operational_data(EXPORT_STUDENTS)
            course_export = service.export_operational_data(EXPORT_COURSES)
            mark_export = service.export_operational_data(EXPORT_MARKS)
            system_export = service.export_report(REPORT_SYSTEM_OVERVIEW)
            low_export = service.export_report(
                REPORT_LOW_ATTENDANCE,
                course_code="PYF201",
                threshold_percentage="80",
            )
            performance_export = service.export_report(
                REPORT_ASSESSMENT_PERFORMANCE,
                assessment_id=str(assessment.assessment_id),
            )

            self.assertEqual(before_export, operational_table_counts(config.paths.database_path))
            for result in (
                student_export,
                course_export,
                mark_export,
                system_export,
                low_export,
                performance_export,
            ):
                self.assertTrue(result.output_path.is_relative_to(config.paths.export_dir))
                self.assertTrue(result.output_path.exists())

            student_rows = self._read_csv(student_export.output_path)
            course_rows = self._read_csv(course_export.output_path)
            mark_rows = self._read_csv(mark_export.output_path)
            low_rows = self._read_csv(low_export.output_path)
            performance_rows = self._read_csv(performance_export.output_path)
            overview = ReportService(config.paths.database_path).get_system_overview()
            system_text = system_export.output_path.read_text(encoding="utf-8")

            self.assertTrue(any(row["first_name"] == "Lebo, Jr" for row in student_rows))
            self.assertTrue(any(row["last_name"] == "Zoë" for row in student_rows))
            self.assertTrue(any(row["fee_amount"] == "99.99" for row in course_rows))
            self.assertTrue(any(row["fee_amount"] == "1.25" for row in course_rows))
            self.assertTrue(any(row["mark_obtained"] == "0" for row in mark_rows))
            self.assertTrue(any(row["mark_obtained"] == "75.5" for row in mark_rows))
            self.assertTrue(any(row["student_number"] == "STU-1002" for row in low_rows))
            self.assertTrue(any(row["student_number"] == "STU-1001" and row["percentage"] == "0.00" for row in performance_rows))
            self.assertTrue(any(row["student_number"] == "STU-1002" and row["percentage"] == "75.50" for row in performance_rows))
            self.assertIn(f"{'Students':<30}: {overview.student_count}", system_text)

            self._write_csv(
                config.paths.import_dir / "bad-courses.csv",
                IMPORT_SCHEMAS[IMPORT_COURSES].headers,
                [
                    {
                        "course_code": "PYF201",
                        "course_name": "Duplicate",
                        "description": "",
                        "fee_amount": "0",
                        "status": "active",
                    },
                    {
                        "course_code": "NEW201",
                        "course_name": "Should Not Persist",
                        "description": "",
                        "fee_amount": "0",
                        "status": "active",
                    },
                ],
            )
            invalid_preview = service.preview_import(IMPORT_COURSES, "bad-courses.csv")
            self.assertFalse(invalid_preview.is_importable)
            with self.assertRaises(ImportValidationError):
                service.commit_import(invalid_preview)
            self.assertEqual(before_export, operational_table_counts(config.paths.database_path))

            recent_names = {file_info.filename for file_info in service.list_recent_exports()}
            self.assertIn(student_export.output_path.name, recent_names)
            self.assertIn(performance_export.output_path.name, recent_names)

    def _write_csv(
        self,
        path: Path,
        headers: tuple[str, ...],
        rows: list[dict[str, object]],
    ) -> None:
        with open(path, "w", encoding="utf-8", newline="") as file_object:
            writer = csv.DictWriter(file_object, fieldnames=list(headers))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        with open(path, "r", encoding="utf-8", newline="") as file_object:
            return list(csv.DictReader(file_object))


if __name__ == "__main__":
    unittest.main()
