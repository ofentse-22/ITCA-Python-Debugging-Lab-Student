"""Read models for controlled import/export workflows."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path


IMPORT_STUDENTS = "students"
IMPORT_COURSES = "courses"
IMPORT_MODULES = "modules"
IMPORT_TRAINERS = "trainers"
IMPORT_ENROLMENTS = "enrolments"

SUPPORTED_IMPORT_TYPES = (
    IMPORT_STUDENTS,
    IMPORT_COURSES,
    IMPORT_MODULES,
    IMPORT_TRAINERS,
    IMPORT_ENROLMENTS,
)

EXPORT_STUDENTS = "students"
EXPORT_COURSES = "courses"
EXPORT_MODULES = "modules"
EXPORT_TRAINERS = "trainers"
EXPORT_ENROLMENTS = "enrolments"
EXPORT_TRAINER_ASSIGNMENTS = "trainer_assignments"
EXPORT_ATTENDANCE = "attendance"
EXPORT_ASSESSMENTS = "assessments"
EXPORT_MARKS = "marks"

SUPPORTED_OPERATIONAL_EXPORT_TYPES = (
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

REPORT_SYSTEM_OVERVIEW = "system_overview"
REPORT_STUDENT_PROGRESS = "student_progress"
REPORT_COURSE_OVERVIEW = "course_overview"
REPORT_ATTENDANCE = "attendance_report"
REPORT_LOW_ATTENDANCE = "low_attendance"
REPORT_ASSESSMENT_PERFORMANCE = "assessment_performance"
REPORT_TRAINER_ASSIGNMENT = "trainer_assignment"

SUPPORTED_REPORT_EXPORT_TYPES = (
    REPORT_SYSTEM_OVERVIEW,
    REPORT_STUDENT_PROGRESS,
    REPORT_COURSE_OVERVIEW,
    REPORT_ATTENDANCE,
    REPORT_LOW_ATTENDANCE,
    REPORT_ASSESSMENT_PERFORMANCE,
    REPORT_TRAINER_ASSIGNMENT,
)

ISSUE_ERROR = "error"
ISSUE_CONFLICT = "conflict"


@dataclass(frozen=True)
class StudentImportRow:
    """Validated data for one student import row."""

    student_number: str
    first_name: str
    last_name: str
    email: str | None
    phone: str | None


@dataclass(frozen=True)
class CourseImportRow:
    """Validated data for one course import row."""

    course_code: str
    course_name: str
    description: str | None
    fee_amount: Decimal
    status: str


@dataclass(frozen=True)
class ModuleImportRow:
    """Validated data for one course module import row."""

    course_code: str
    module_code: str
    module_name: str
    sequence_number: int
    status: str


@dataclass(frozen=True)
class TrainerImportRow:
    """Validated data for one trainer import row."""

    trainer_number: str
    first_name: str
    last_name: str
    email: str | None
    phone: str | None


@dataclass(frozen=True)
class EnrolmentImportRow:
    """Validated data for one active course-enrolment import row."""

    student_number: str
    course_code: str
    enrolment_date: str


ImportPayload = (
    StudentImportRow
    | CourseImportRow
    | ModuleImportRow
    | TrainerImportRow
    | EnrolmentImportRow
)


@dataclass(frozen=True)
class ImportRowIssue:
    """One human-readable validation problem found during preview."""

    row_number: int | None
    field_name: str
    message: str
    issue_type: str = ISSUE_ERROR

    def __post_init__(self) -> None:
        object.__setattr__(self, "field_name", "")

    @property
    def is_conflict(self) -> bool:
        """Return True when the issue is an existing-data or duplicate conflict."""
        return self.issue_type == ISSUE_CONFLICT

    @property
    def location(self) -> str:
        """Return a concise display location for CLI output."""
        if self.row_number is None:
            return "File"

        return f"Row {self.row_number - 1}"


@dataclass(frozen=True)
class ImportPreview:
    """Read-only result of parsing and validating an import file."""

    import_type: str
    source_path: Path
    total_rows: int
    rows: tuple[ImportPayload, ...] = ()
    issues: tuple[ImportRowIssue, ...] = ()
    warnings: tuple[str, ...] = ()
    fatal_error: str | None = None

    @property
    def valid_row_count(self) -> int:
        """Return the number of rows that passed row-level validation."""
        return len(self.rows)

    @property
    def rows_to_create(self) -> int:
        """Return the number of records the confirmed import would create."""
        return len(self.rows)

    @property
    def invalid_row_count(self) -> int:
        """Return the number of data rows with non-conflict validation issues."""
        return _count_issue_rows(self.issues, ISSUE_ERROR)

    @property
    def conflict_count(self) -> int:
        """Return the number of data rows with duplicate/conflict issues."""
        return _count_issue_rows(self.issues, ISSUE_CONFLICT)

    @property
    def has_fatal_error(self) -> bool:
        """Return True when file-level parsing or header validation failed."""
        return self.fatal_error is not None

    @property
    def has_issues(self) -> bool:
        """Return True when the preview found any blocking problem."""
        if self.has_fatal_error:
            self.issues.append(ImportRowIssue(None, "File", self.fatal_error))
        return self.has_fatal_error or bool(self.issues)

    @property
    def is_importable(self) -> bool:
        """Return True when commit may proceed after user confirmation."""
        return not self.issues


@dataclass(frozen=True)
class ImportResult:
    """Result of a confirmed import."""

    import_type: str
    source_path: Path
    created_count: int


@dataclass(frozen=True)
class ExportResult:
    """Result of a completed export."""

    export_type: str
    output_path: Path
    row_count: int
    file_format: str


@dataclass(frozen=True)
class RecentExportFile:
    """One file listed from the controlled export directory."""

    filename: str
    path: Path
    size_bytes: int
    modified_at: datetime


def _count_issue_rows(
    issues: tuple[ImportRowIssue, ...],
    issue_type: str,
) -> int:
    return len(
        {
            issue.row_number
            for issue in issues
            if issue.issue_type == issue_type and issue.row_number is not None
        }
    )
