"""Import/export workflow coordination."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import logging

from ..cli.report_cli import (
    format_course_attendance_report,
    format_course_overview_report,
    format_student_progress_report,
    format_system_overview_report,
    format_trainer_assignment_report,
)
from ..data.decimal_storage import decimal_to_storage
from ..models.course import COURSE_ACTIVE_STATUS, COURSE_STATUSES
from ..models.import_export import (
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
    ISSUE_CONFLICT,
    CourseImportRow,
    EnrolmentImportRow,
    ExportResult,
    ImportPayload,
    ImportPreview,
    ImportResult,
    ImportRowIssue,
    ModuleImportRow,
    REPORT_ASSESSMENT_PERFORMANCE,
    REPORT_ATTENDANCE,
    REPORT_COURSE_OVERVIEW,
    REPORT_LOW_ATTENDANCE,
    REPORT_STUDENT_PROGRESS,
    REPORT_SYSTEM_OVERVIEW,
    REPORT_TRAINER_ASSIGNMENT,
    RecentExportFile,
    StudentImportRow,
    TrainerImportRow,
)
from ..models.module import MODULE_STATUSES
from ..models.student import ACTIVE_STATUS
from ..repositories.import_export_repository import ImportExportRepository
from ..services.assessment_service import round_percentage_for_display
from ..services.report_service import ReportService
from ..storage.csv_io import CsvRow, read_csv_rows, write_csv_rows
from ..storage.text_export import write_text_file
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    ExportFileError,
    ImportExportError,
    ImportValidationError,
    PathSafetyError,
    RecordNotFoundError,
    ValidationError,
)
from ..utils.logging_setup import get_application_logger
from ..utils.path_safety import resolve_relative_path
from ..utils.validators import (
    normalize_course_code,
    normalize_course_name,
    normalize_description,
    normalize_fee_amount,
    normalize_iso_date,
    normalize_module_code,
    normalize_module_name,
    normalize_sequence_number,
    normalize_status,
    normalize_student_email,
    normalize_student_name,
    normalize_student_number,
    normalize_student_phone,
    normalize_trainer_email,
    normalize_trainer_name,
    normalize_trainer_number,
    normalize_trainer_phone,
)


Clock = Callable[[], datetime]


@dataclass(frozen=True)
class CsvSchema:
    """Explicit header order for one CSV import or export."""

    headers: tuple[str, ...]


IMPORT_LABELS = {
    IMPORT_STUDENTS: "Students",
    IMPORT_COURSES: "Courses",
    IMPORT_MODULES: "Modules",
    IMPORT_TRAINERS: "Trainers",
    IMPORT_ENROLMENTS: "Enrolments",
}

OPERATIONAL_EXPORT_LABELS = {
    EXPORT_STUDENTS: "Students",
    EXPORT_COURSES: "Courses",
    EXPORT_MODULES: "Modules",
    EXPORT_TRAINERS: "Trainers",
    EXPORT_ENROLMENTS: "Enrolments",
    EXPORT_TRAINER_ASSIGNMENTS: "Trainer Assignments",
    EXPORT_ATTENDANCE: "Attendance",
    EXPORT_ASSESSMENTS: "Assessments",
    EXPORT_MARKS: "Marks / Results",
}

REPORT_EXPORT_LABELS = {
    REPORT_SYSTEM_OVERVIEW: "System Overview",
    REPORT_STUDENT_PROGRESS: "Student Progress",
    REPORT_COURSE_OVERVIEW: "Course Overview",
    REPORT_ATTENDANCE: "Attendance Report",
    REPORT_LOW_ATTENDANCE: "Low Attendance",
    REPORT_ASSESSMENT_PERFORMANCE: "Assessment Performance",
    REPORT_TRAINER_ASSIGNMENT: "Trainer Assignment",
}

IMPORT_SCHEMAS = {
    IMPORT_STUDENTS: CsvSchema(
        ("student_number", "first_name", "last_name", "email", "phone")
    ),
    IMPORT_COURSES: CsvSchema(
        ("course_code", "course_name", "description", "fee_amount", "status")
    ),
    IMPORT_MODULES: CsvSchema(
        ("course_code", "module_code", "module_name", "sequence_number", "status")
    ),
    IMPORT_TRAINERS: CsvSchema(
        ("trainer_number", "first_name", "last_name", "email", "phone")
    ),
    IMPORT_ENROLMENTS: CsvSchema(
        ("student_number", "course_code", "enrolment_date")
    ),
}

OPERATIONAL_EXPORT_SCHEMAS = {
    EXPORT_STUDENTS: CsvSchema(
        ("student_number", "first_name", "last_name", "email", "phone", "status")
    ),
    EXPORT_COURSES: CsvSchema(
        ("course_code", "course_name", "description", "fee_amount", "status")
    ),
    EXPORT_MODULES: CsvSchema(
        ("course_code", "module_code", "module_name", "sequence_number", "status")
    ),
    EXPORT_TRAINERS: CsvSchema(
        ("trainer_number", "first_name", "last_name", "email", "phone", "status")
    ),
    EXPORT_ENROLMENTS: CsvSchema(
        (
            "student_number",
            "course_code",
            "enrolment_date",
            "status",
            "cancelled_at",
            "cancellation_reason",
        )
    ),
    EXPORT_TRAINER_ASSIGNMENTS: CsvSchema(
        ("trainer_number", "course_code", "assigned_from", "assigned_to", "status")
    ),
    EXPORT_ATTENDANCE: CsvSchema(
        ("course_code", "session_date", "topic", "student_number", "status", "notes")
    ),
    EXPORT_ASSESSMENTS: CsvSchema(
        (
            "assessment_id",
            "course_code",
            "module_code",
            "assessment_name",
            "assessment_type",
            "max_mark",
            "weight",
            "pass_mark",
            "status",
        )
    ),
    EXPORT_MARKS: CsvSchema(
        (
            "assessment_id",
            "course_code",
            "module_code",
            "assessment_name",
            "assessment_type",
            "student_number",
            "mark_obtained",
            "captured_at",
            "notes",
        )
    ),
}

LOW_ATTENDANCE_REPORT_HEADERS = (
    "group",
    "course_code",
    "threshold_percentage",
    "student_number",
    "student_name",
    "record_count",
    "attended_count",
    "eligible_records",
    "attendance_percentage",
)

ASSESSMENT_PERFORMANCE_REPORT_HEADERS = (
    "assessment_id",
    "assessment_name",
    "student_number",
    "student_name",
    "eligibility",
    "mark_obtained",
    "percentage",
    "result_state",
    "captured_at",
    "notes",
)


class ImportExportService:
    """Coordinate safe import preview, confirmed import, and exports."""

    def __init__(
        self,
        database_path: Path,
        import_dir: Path,
        export_dir: Path,
        repository: ImportExportRepository | None = None,
        report_service: ReportService | None = None,
        clock: Clock | None = None,
        logger: logging.Logger | None = None,
    ):
        self.database_path = Path(database_path)
        self.import_dir = Path(import_dir)
        self.export_dir = Path(export_dir)
        self.repository = repository or ImportExportRepository(self.database_path)
        self.report_service = report_service or ReportService(self.database_path)
        self.clock = clock or datetime.now
        self.logger = logger or get_application_logger()

    def preview_import(self, import_type: str, source_name: str | Path) -> ImportPreview:
        """Parse and validate an import file without changing the database."""
        schema = _get_import_schema(import_type)

        try:
            source_path = self._resolve_import_path(source_name)
            csv_result = read_csv_rows(source_path, schema.headers)
        except (ImportValidationError, PathSafetyError) as error:
            self.logger.warning("Import preview failed")
            return ImportPreview(
                import_type=import_type,
                source_path=Path(source_name),
                total_rows=0,
                fatal_error=str(error),
            )
        except:
            self.logger.warning("Import preview failed")
            return ImportPreview(
                import_type=import_type,
                source_path=Path(source_name),
                total_rows=0,
                fatal_error="Import preview failed.",
            )

        issues: list[ImportRowIssue] = []
        rows: list[ImportPayload] = []
        seen = _new_seen_values()

        for csv_row in csv_result.rows:
            row_issue_count = len(issues)
            payload = self._validate_row(import_type, csv_row, seen, issues)
            if len(issues) > row_issue_count:
                del issues[row_issue_count:]
                continue
            if payload is not None:
                rows.append(payload)

        preview = ImportPreview(
            import_type=import_type,
            source_path=source_path,
            total_rows=len(csv_result.rows),
            rows=tuple(rows),
            issues=tuple(issues),
        )
        self.logger.info("Import preview completed")
        return preview

    def commit_import(self, preview: ImportPreview) -> ImportResult:
        """Commit a previously reviewed import preview in one transaction."""
        if not preview.is_importable:
            raise ImportValidationError(
                "Import cannot proceed until errors are corrected."
            )

        try:
            created_count = self._commit_payload_rows(preview)
        except (
            DatabaseError,
            DuplicateRecordError,
            ImportExportError,
            RecordNotFoundError,
            ValidationError,
        ):
            self.logger.exception("Import commit failed")
            raise

        self.logger.info("Import committed")
        return ImportResult(
            import_type=preview.import_type,
            source_path=preview.source_path,
            created_count=created_count,
        )

    def export_operational_data(self, export_type: str) -> ExportResult:
        """Export one operational dataset as controlled CSV."""
        schema = _get_operational_export_schema(export_type)

        try:
            rows = self._operational_export_rows(export_type)
            output_path = self._next_export_path(f"operational-{export_type}", "csv")
            row_count = write_csv_rows(output_path, schema.headers, rows)
        except (DatabaseError, ExportFileError, PathSafetyError):
            self.logger.exception("Operational export failed")
            raise

        self.logger.info("Operational export completed")
        return ExportResult(export_type, output_path, row_count, "csv")

    def export_report(self, report_type: str, **filters) -> ExportResult:
        """Export one Phase 8 report as text or CSV."""
        if report_type not in REPORT_EXPORT_LABELS:
            raise ValidationError(f"Unsupported report export type: {report_type}")

        try:
            result = self._export_report(report_type, filters)
        except (
            DatabaseError,
            ExportFileError,
            PathSafetyError,
            RecordNotFoundError,
            ValidationError,
        ):
            self.logger.exception("Report export failed")
            raise

        self.logger.info("Report export completed")
        return result

    def list_recent_exports(self, limit: int = 10) -> tuple[RecentExportFile, ...]:
        """List recent files directly inside the controlled export directory."""
        try:
            self.export_dir.mkdir(parents=True, exist_ok=True)
            export_files = []
            for path in self.export_dir.iterdir():
                if not path.is_file():
                    continue
                stat_result = path.stat()
                export_files.append(
                    RecentExportFile(
                        filename=path.name,
                        path=path,
                        size_bytes=stat_result.st_size,
                        modified_at=datetime.fromtimestamp(stat_result.st_mtime),
                    )
                )

            return tuple(export_files[:limit])
        except OSError as error:
            raise ExportFileError("Recent export files could not be listed.") from error

    def _resolve_import_path(self, source_name: str | Path) -> Path:
        text = str(source_name).strip()
        if not text:
            raise ImportValidationError("Import filename is required.")

        return resolve_relative_path(self.import_dir, text)

    def _validate_row(
        self,
        import_type: str,
        csv_row: CsvRow,
        seen: dict[str, set[object]],
        issues: list[ImportRowIssue],
    ) -> ImportPayload | None:
        if import_type == IMPORT_STUDENTS:
            return self._validate_student_row(csv_row, seen, issues)
        if import_type == IMPORT_COURSES:
            return self._validate_course_row(csv_row, seen, issues)
        if import_type == IMPORT_MODULES:
            return self._validate_module_row(csv_row, seen, issues)
        if import_type == IMPORT_TRAINERS:
            return self._validate_trainer_row(csv_row, seen, issues)
        if import_type == IMPORT_ENROLMENTS:
            return self._validate_enrolment_row(csv_row, seen, issues)

        raise ValidationError(f"Unsupported import type: {import_type}")

    def _validate_student_row(
        self,
        csv_row: CsvRow,
        seen: dict[str, set[object]],
        issues: list[ImportRowIssue],
    ) -> StudentImportRow | None:
        issue_count = len(issues)
        student_number = _normalize_field(
            csv_row,
            "student_number",
            normalize_student_number,
            issues,
        )
        first_name = _normalize_field(
            csv_row,
            "first_name",
            lambda value: normalize_student_name(value, "First name"),
            issues,
        )
        last_name = _normalize_field(
            csv_row,
            "last_name",
            lambda value: normalize_student_name(value, "Last name"),
            issues,
        )
        email = _normalize_field(csv_row, "email", normalize_student_email, issues)
        phone = _normalize_field(csv_row, "phone", normalize_student_phone, issues)
        if len(issues) > issue_count:
            return None

        if not _claim_unique(
            seen["student_numbers"],
            student_number,
            csv_row,
            "student_number",
            "Student number appears more than once in this file.",
            issues,
        ):
            return None
        if email is not None and not _claim_unique(
            seen["student_emails"],
            email,
            csv_row,
            "email",
            "Email address appears more than once in this file.",
            issues,
        ):
            return None
        if self.repository.get_student_context(student_number) is not None:
            _add_conflict(
                csv_row,
                "student_number",
                "Student number already exists.",
                issues,
            )
            return None
        if self.repository.student_email_exists(email):
            _add_conflict(csv_row, "email", "Email address already exists.", issues)
            return None

        return StudentImportRow(student_number, first_name, last_name, email, phone)

    def _validate_course_row(
        self,
        csv_row: CsvRow,
        seen: dict[str, set[object]],
        issues: list[ImportRowIssue],
    ) -> CourseImportRow | None:
        issue_count = len(issues)
        course_code = _normalize_field(
            csv_row,
            "course_code",
            normalize_course_code,
            issues,
        )
        course_name = _normalize_field(
            csv_row,
            "course_name",
            normalize_course_name,
            issues,
        )
        description = _normalize_field(
            csv_row,
            "description",
            normalize_description,
            issues,
        )
        fee_amount = _normalize_field(
            csv_row,
            "fee_amount",
            normalize_fee_amount,
            issues,
        )
        status = _normalize_field(
            csv_row,
            "status",
            lambda value: normalize_status(value, "Course status", COURSE_STATUSES),
            issues,
        )
        if len(issues) > issue_count:
            return None

        if not _claim_unique(
            seen["course_codes"],
            course_code,
            csv_row,
            "course_code",
            "Course code appears more than once in this file.",
            issues,
        ):
            return None
        if self.repository.get_course_context(course_code) is not None:
            _add_conflict(csv_row, "course_code", "Course code already exists.", issues)
            return None

        return CourseImportRow(
            course_code=course_code,
            course_name=course_name,
            description=description,
            fee_amount=fee_amount,
            status=status,
        )

    def _validate_module_row(
        self,
        csv_row: CsvRow,
        seen: dict[str, set[object]],
        issues: list[ImportRowIssue],
    ) -> ModuleImportRow | None:
        issue_count = len(issues)
        course_code = _normalize_field(
            csv_row,
            "course_code",
            normalize_course_code,
            issues,
        )
        module_code = _normalize_field(
            csv_row,
            "module_code",
            normalize_module_code,
            issues,
        )
        module_name = _normalize_field(
            csv_row,
            "module_name",
            normalize_module_name,
            issues,
        )
        sequence_number = _normalize_field(
            csv_row,
            "sequence_number",
            normalize_sequence_number,
            issues,
        )
        status = _normalize_field(
            csv_row,
            "status",
            lambda value: normalize_status(value, "Module status", MODULE_STATUSES),
            issues,
        )
        if len(issues) > issue_count:
            return None

        module_key = (course_code, module_code)
        sequence_key = (course_code, sequence_number)
        if not _claim_unique(
            seen["module_keys"],
            module_key,
            csv_row,
            "module_code",
            "Module code appears more than once for this course in this file.",
            issues,
        ):
            return None
        if not _claim_unique(
            seen["module_sequences"],
            sequence_key,
            csv_row,
            "sequence_number",
            "Module sequence appears more than once for this course in this file.",
            issues,
        ):
            return None

        if self.repository.get_course_context(course_code) is None:
            _add_error(csv_row, "course_code", "Course code was not found.", issues)
            return None
        if self.repository.module_exists(course_code, module_code):
            _add_conflict(
                csv_row,
                "module_code",
                "Module code already exists for this course.",
                issues,
            )
            return None
        if self.repository.module_sequence_exists(course_code, sequence_number):
            _add_conflict(
                csv_row,
                "sequence_number",
                "Module sequence already exists for this course.",
                issues,
            )
            return None

        return ModuleImportRow(
            course_code=course_code,
            module_code=module_code,
            module_name=module_name,
            sequence_number=sequence_number,
            status=status,
        )

    def _validate_trainer_row(
        self,
        csv_row: CsvRow,
        seen: dict[str, set[object]],
        issues: list[ImportRowIssue],
    ) -> TrainerImportRow | None:
        issue_count = len(issues)
        trainer_number = _normalize_field(
            csv_row,
            "trainer_number",
            normalize_trainer_number,
            issues,
        )
        first_name = _normalize_field(
            csv_row,
            "first_name",
            lambda value: normalize_trainer_name(value, "First name"),
            issues,
        )
        last_name = _normalize_field(
            csv_row,
            "last_name",
            lambda value: normalize_trainer_name(value, "Last name"),
            issues,
        )
        email = _normalize_field(csv_row, "email", normalize_trainer_email, issues)
        phone = _normalize_field(csv_row, "phone", normalize_trainer_phone, issues)
        if len(issues) > issue_count:
            return None

        if not _claim_unique(
            seen["trainer_numbers"],
            trainer_number,
            csv_row,
            "trainer_number",
            "Trainer number appears more than once in this file.",
            issues,
        ):
            return None
        if email is not None and not _claim_unique(
            seen["trainer_emails"],
            email,
            csv_row,
            "email",
            "Email address appears more than once in this file.",
            issues,
        ):
            return None
        if self.repository.get_trainer_context(trainer_number) is not None:
            _add_conflict(
                csv_row,
                "trainer_number",
                "Trainer number already exists.",
                issues,
            )
            return None
        if self.repository.trainer_email_exists(email):
            _add_conflict(csv_row, "email", "Email address already exists.", issues)
            return None

        return TrainerImportRow(trainer_number, first_name, last_name, email, phone)

    def _validate_enrolment_row(
        self,
        csv_row: CsvRow,
        seen: dict[str, set[object]],
        issues: list[ImportRowIssue],
    ) -> EnrolmentImportRow | None:
        issue_count = len(issues)
        student_number = _normalize_field(
            csv_row,
            "student_number",
            normalize_student_number,
            issues,
        )
        course_code = _normalize_field(
            csv_row,
            "course_code",
            normalize_course_code,
            issues,
        )
        enrolment_date = _normalize_field(
            csv_row,
            "enrolment_date",
            lambda value: normalize_iso_date(value, "Enrolment date"),
            issues,
        )
        if len(issues) > issue_count:
            return None

        enrolment_key = (student_number, course_code)
        if not _claim_unique(
            seen["enrolment_keys"],
            enrolment_key,
            csv_row,
            "student_number",
            "Student/course enrolment appears more than once in this file.",
            issues,
        ):
            return None

        student_context = self.repository.get_student_context(student_number)
        if student_context is None:
            _add_error(csv_row, "student_number", "Student number was not found.", issues)
            return None
        if student_context[1] != ACTIVE_STATUS:
            _add_error(
                csv_row,
                "student_number",
                "Student must be active before enrolling in a course.",
                issues,
            )
            return None

        course_context = self.repository.get_course_context(course_code)
        if course_context is None:
            _add_error(csv_row, "course_code", "Course code was not found.", issues)
            return None
        if course_context[1] != COURSE_ACTIVE_STATUS:
            _add_error(
                csv_row,
                "course_code",
                "Course must be active before enrolling students.",
                issues,
            )
            return None

        if self.repository.active_enrolment_exists(student_number, course_code):
            _add_conflict(
                csv_row,
                "student_number",
                "Student is already actively enrolled in this course.",
                issues,
            )
            return None

        return EnrolmentImportRow(student_number, course_code, enrolment_date)

    def _commit_payload_rows(self, preview: ImportPreview) -> int:
        if preview.import_type == IMPORT_STUDENTS:
            return self.repository.create_students(_typed_rows(preview, StudentImportRow))
        if preview.import_type == IMPORT_COURSES:
            return self.repository.create_courses(_typed_rows(preview, CourseImportRow))
        if preview.import_type == IMPORT_MODULES:
            return self.repository.create_modules(_typed_rows(preview, ModuleImportRow))
        if preview.import_type == IMPORT_TRAINERS:
            return self.repository.create_trainers(_typed_rows(preview, TrainerImportRow))
        if preview.import_type == IMPORT_ENROLMENTS:
            created_count = 0
            for row in _typed_rows(preview, EnrolmentImportRow):
                created_count += self.repository.create_enrolments((row,))
            return created_count

        raise ValidationError(f"Unsupported import type: {preview.import_type}")

    def _operational_export_rows(self, export_type: str) -> list[dict[str, object]]:
        if export_type == EXPORT_STUDENTS:
            return self.repository.list_student_export_rows()
        if export_type == EXPORT_COURSES:
            return self.repository.list_course_export_rows()
        if export_type == EXPORT_MODULES:
            return self.repository.list_module_export_rows()
        if export_type == EXPORT_TRAINERS:
            return self.repository.list_trainer_export_rows()
        if export_type == EXPORT_ENROLMENTS:
            return self.repository.list_enrolment_export_rows()
        if export_type == EXPORT_TRAINER_ASSIGNMENTS:
            return self.repository.list_trainer_assignment_export_rows()
        if export_type == EXPORT_ATTENDANCE:
            return self.repository.list_attendance_export_rows()
        if export_type == EXPORT_ASSESSMENTS:
            return self.repository.list_assessment_export_rows()
        if export_type == EXPORT_MARKS:
            return self.repository.list_mark_export_rows()

        raise ValidationError(f"Unsupported operational export type: {export_type}")

    def _export_report(self, report_type: str, filters: dict[str, object]) -> ExportResult:
        if report_type == REPORT_SYSTEM_OVERVIEW:
            report = self.report_service.get_system_overview()
            return self._write_report_text(
                report_type,
                format_system_overview_report(report),
            )

        if report_type == REPORT_STUDENT_PROGRESS:
            student_number = _required_filter(filters, "student_number", "Student number")
            report = self.report_service.get_student_progress(student_number)
            return self._write_report_text(
                report_type,
                format_student_progress_report(report),
            )

        if report_type == REPORT_COURSE_OVERVIEW:
            course_code = _required_filter(filters, "course_code", "Course code")
            report = self.report_service.get_course_overview(course_code)
            return self._write_report_text(
                report_type,
                format_course_overview_report(report),
            )

        if report_type == REPORT_ATTENDANCE:
            course_code = _required_filter(filters, "course_code", "Course code")
            report = self.report_service.get_course_attendance_report(
                course_code,
                date_from=_optional_filter(filters, "date_from"),
                date_to=_optional_filter(filters, "date_to"),
            )
            return self._write_report_text(
                report_type,
                format_course_attendance_report(report),
            )

        if report_type == REPORT_LOW_ATTENDANCE:
            course_code = _required_filter(filters, "course_code", "Course code")
            threshold = _required_filter(
                filters,
                "threshold_percentage",
                "Attendance threshold",
            )
            report = self.report_service.get_low_attendance_students(
                course_code,
                threshold,
            )
            return self._write_report_csv(
                report_type,
                LOW_ATTENDANCE_REPORT_HEADERS,
                _low_attendance_report_rows(report),
            )

        if report_type == REPORT_ASSESSMENT_PERFORMANCE:
            assessment_id = _required_filter(filters, "assessment_id", "Assessment ID")
            report = self.report_service.get_assessment_performance(assessment_id)
            return self._write_report_csv(
                report_type,
                ASSESSMENT_PERFORMANCE_REPORT_HEADERS,
                _assessment_performance_report_rows(report),
            )

        if report_type == REPORT_TRAINER_ASSIGNMENT:
            trainer_number = _required_filter(filters, "trainer_number", "Trainer number")
            report = self.report_service.get_trainer_assignment_report(trainer_number)
            return self._write_report_text(
                report_type,
                format_trainer_assignment_report(report),
            )

        raise ValidationError(f"Unsupported report export type: {report_type}")

    def _write_report_text(self, report_type: str, lines: list[str]) -> ExportResult:
        output_path = self._next_export_path(f"report-{report_type}", "txt")
        line_count = write_text_file(output_path, lines)
        return ExportResult(report_type, output_path, line_count, "txt")

    def _write_report_csv(
        self,
        report_type: str,
        headers: tuple[str, ...],
        rows: list[dict[str, object]],
    ) -> ExportResult:
        output_path = self._next_export_path(f"report-{report_type}", "csv")
        row_count = write_csv_rows(output_path, headers, rows)
        return ExportResult(report_type, output_path, row_count, "csv")

    def _next_export_path(self, export_type: str, extension: str) -> Path:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        safe_slug = _slug(export_type)
        safe_extension = _slug(extension)
        timestamp = self.clock().strftime("%Y%m%d-%H%M%S")
        filename = f"{safe_slug}-{timestamp}.{safe_extension}"
        path = resolve_relative_path(self.export_dir, filename)

        counter = 2
        while path.exists():
            filename = f"{safe_slug}-{timestamp}-{counter}.{safe_extension}"
            path = resolve_relative_path(self.export_dir, filename)
            counter += 1

        return path


def _get_import_schema(import_type: str) -> CsvSchema:
    try:
        return IMPORT_SCHEMAS[import_type]
    except KeyError as error:
        raise ValidationError(f"Unsupported import type: {import_type}") from error


def _get_operational_export_schema(export_type: str) -> CsvSchema:
    try:
        return OPERATIONAL_EXPORT_SCHEMAS[export_type]
    except KeyError as error:
        raise ValidationError(
            f"Unsupported operational export type: {export_type}"
        ) from error


def _new_seen_values() -> dict[str, set[object]]:
    return {
        "student_numbers": set(),
        "student_emails": set(),
        "course_codes": set(),
        "module_keys": set(),
        "module_sequences": set(),
        "trainer_numbers": set(),
        "trainer_emails": set(),
        "enrolment_keys": set(),
    }


def _normalize_field(
    csv_row: CsvRow,
    field_name: str,
    normalizer: Callable[[str | None], object],
    issues: list[ImportRowIssue],
):
    try:
        return normalizer(csv_row.data[field_name.replace("_", "-")])
    except ValidationError as error:
        _add_error(csv_row, field_name, str(error), issues)
        return None


def _claim_unique(
    seen_values: set[object],
    value: object,
    csv_row: CsvRow,
    field_name: str,
    message: str,
    issues: list[ImportRowIssue],
) -> bool:
    if value in seen_values:
        _add_conflict(csv_row, field_name, message, issues)
        return False

    seen_values.add(value)
    return True


def _add_error(
    csv_row: CsvRow,
    field_name: str,
    message: str,
    issues: list[ImportRowIssue],
) -> None:
    issues.append(ImportRowIssue(csv_row.row_number, field_name, message))


def _add_conflict(
    csv_row: CsvRow,
    field_name: str,
    message: str,
    issues: list[ImportRowIssue],
) -> None:
    issues.append(
        ImportRowIssue(
            row_number=csv_row.row_number,
            field_name=field_name,
            message=message,
            issue_type=ISSUE_CONFLICT,
        )
    )


def _typed_rows(
    preview: ImportPreview,
    row_type,
):
    return tuple(row for row in preview.rows if isinstance(row, row_type))


def _required_filter(
    filters: dict[str, object],
    key: str,
    field_name: str,
) -> str:
    value = filters.get(key)
    if value is None or not str(value).strip():
        raise ValidationError(f"{field_name} is required.")

    return str(value).strip()


def _optional_filter(filters: dict[str, object], key: str) -> str | None:
    value = filters.get(key)
    if value is None or not str(value).strip():
        return None

    return str(value).strip()


def _low_attendance_report_rows(report) -> list[dict[str, object]]:
    rows = []
    for group_name, report_rows in (
        ("below_threshold", report.students_below_threshold),
        ("no_calculable_attendance", report.students_without_calculable_attendance),
    ):
        for row in report_rows:
            rows.append(
                {
                    "group": group_name,
                    "course_code": report.course.course_code,
                    "threshold_percentage": f"{report.threshold_percentage:.2f}",
                    "student_number": row.student.student_number,
                    "student_name": row.student.full_name,
                    "record_count": row.summary.record_count,
                    "attended_count": row.summary.attended_count,
                    "eligible_records": row.summary.percentage_denominator,
                    "attendance_percentage": _format_float_percentage(
                        row.summary.attendance_percentage
                    ),
                }
            )

    return rows


def _assessment_performance_report_rows(report) -> list[dict[str, object]]:
    rows = []
    for row in report.students:
        rows.append(
            {
                "assessment_id": report.assessment.assessment_id,
                "assessment_name": report.assessment.assessment_name,
                "student_number": row.student.student_number,
                "student_name": row.student.full_name,
                "eligibility": (
                    "eligible" if row.is_currently_eligible else "historical"
                ),
                "mark_obtained": _format_optional_decimal(row.mark_obtained),
                "percentage": _format_optional_decimal_percentage(row.percentage),
                "result_state": row.result_state or "",
                "captured_at": row.captured_at,
                "notes": row.notes,
            }
        )

    return rows


def _format_optional_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""

    return decimal_to_storage(value)


def _format_optional_decimal_percentage(value: Decimal | None) -> str:
    if value is None:
        return ""

    return f"{round_percentage_for_display(value):.2f}"


def _format_float_percentage(value: float | None) -> str:
    if value is None:
        return ""

    return f"{value:.2f}"


def _slug(value: str) -> str:
    parts = []
    previous_dash = False
    for character in str(value).lower():
        if character.isascii() and character.isalnum():
            parts.append(character)
            previous_dash = False
        elif not previous_dash:
            parts.append("-")
            previous_dash = True

    slug = "".join(parts).strip("-")
    return slug or "export"
