"""Structured read models for reports and statistics."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ReportStudent:
    """Student identity fields used in reports."""

    student_id: int
    student_number: str
    first_name: str
    last_name: str
    status: str

    @property
    def full_name(self) -> str:
        """Return the student's display name."""
        return f"{self.first_name} {self.last_name}"


@dataclass(frozen=True)
class ReportCourse:
    """Course identity fields used in reports."""

    course_id: int
    course_code: str
    course_name: str
    status: str


@dataclass(frozen=True)
class ReportModule:
    """Course module fields used in reports."""

    module_id: int
    course_id: int
    module_code: str
    module_name: str
    sequence_number: int
    status: str


@dataclass(frozen=True)
class ReportTrainer:
    """Trainer identity fields used in reports."""

    trainer_id: int
    trainer_number: str
    first_name: str
    last_name: str
    status: str

    @property
    def full_name(self) -> str:
        """Return the trainer's display name."""
        return f"{self.first_name} {self.last_name}"


@dataclass(frozen=True)
class ReportEnrolmentRow:
    """Enrolment row with student and course context."""

    enrolment_id: int
    student_id: int
    student_number: str
    student_first_name: str
    student_last_name: str
    student_name: str
    student_status: str
    course_id: int
    course_code: str
    course_name: str
    course_status: str
    enrolment_date: str
    status: str
    cancelled_at: str | None
    cancellation_reason: str | None

    @property
    def is_active(self) -> bool:
        """Return True when the enrolment is currently active."""
        return self.status == "active"

    @property
    def is_historical(self) -> bool:
        """Return True when the enrolment is no longer active."""
        return self.status != "active"


@dataclass(frozen=True)
class ReportTrainerAssignmentRow:
    """Trainer-course assignment row with trainer and course context."""

    assignment_id: int
    trainer_id: int
    trainer_number: str
    trainer_name: str
    trainer_status: str
    course_id: int
    course_code: str
    course_name: str
    course_status: str
    assigned_from: str
    assigned_to: str | None
    status: str

    @property
    def is_active(self) -> bool:
        """Return True when the assignment is currently active."""
        return self.status == "active"

    @property
    def is_historical(self) -> bool:
        """Return True when the assignment has ended."""
        return self.status != "active"


@dataclass(frozen=True)
class ReportAssessment:
    """Assessment definition fields used in reports."""

    assessment_id: int
    course_id: int
    course_code: str
    course_name: str
    course_status: str
    module_id: int | None
    module_code: str | None
    module_name: str | None
    module_status: str | None
    assessment_name: str
    assessment_type: str
    max_mark: Decimal
    weight: Decimal | None
    pass_mark: Decimal | None
    status: str

    @property
    def module_label(self) -> str:
        """Return a display label for the assessment target."""
        if self.module_id is None:
            return "Course level"

        return f"{self.module_code} - {self.module_name}"

    @property
    def has_pass_mark(self) -> bool:
        """Return True when pass/fail can be classified."""
        return self.pass_mark is not None


@dataclass(frozen=True)
class ReportAttendanceRecordSource:
    """Minimal attendance record data used for report calculations."""

    session_id: int
    course_id: int
    student_id: int
    status: str


@dataclass(frozen=True)
class ReportAttendanceSessionSource:
    """Attendance session counts before percentage calculation."""

    session_id: int
    course_id: int
    session_date: str
    topic: str
    record_count: int
    present_count: int
    late_count: int
    absent_count: int
    excused_count: int
    unknown_count: int


@dataclass(frozen=True)
class AttendanceStatusSummary:
    """Calculated attendance totals for report display."""

    session_count: int
    record_count: int
    present_count: int
    late_count: int
    absent_count: int
    excused_count: int
    unknown_count: int
    percentage_denominator: int
    attendance_percentage: float | None

    @property
    def attended_count(self) -> int:
        """Return statuses that count as attended."""
        return self.present_count + self.late_count

    @property
    def has_records(self) -> bool:
        """Return True when attendance rows exist."""
        return self.record_count > 0

    @property
    def has_percentage(self) -> bool:
        """Return True when a percentage can be calculated."""
        return bool(self.attendance_percentage)


@dataclass(frozen=True)
class CourseAttendanceSummaryRow:
    """One student's attendance summary for a course."""

    course: ReportCourse
    summary: AttendanceStatusSummary


@dataclass(frozen=True)
class AttendanceSessionReportRow:
    """One course session's attendance totals."""

    session_id: int
    session_date: str
    topic: str
    record_count: int
    present_count: int
    late_count: int
    absent_count: int
    excused_count: int
    unknown_count: int
    percentage_denominator: int
    attendance_percentage: float | None

    @property
    def attended_count(self) -> int:
        """Return statuses that count as attended."""
        return self.present_count + self.late_count


@dataclass(frozen=True)
class CourseAttendanceStudentRow:
    """One student's attendance totals in a course attendance report."""

    student: ReportStudent
    summary: AttendanceStatusSummary


@dataclass(frozen=True)
class StudentAssessmentReportRow:
    """One assessment row in a student progress report."""

    assessment: ReportAssessment
    mark_id: int | None
    mark_obtained: Decimal | None
    percentage: Decimal | None
    result_state: str | None
    captured_at: str | None
    notes: str | None

    @property
    def has_mark(self) -> bool:
        """Return True when a mark row exists, including a recorded zero."""
        return self.mark_id is not None

    @property
    def is_missing(self) -> bool:
        """Return True when no mark row has been recorded."""
        return self.mark_id is None

    @property
    def is_unclassified(self) -> bool:
        """Return True when a mark exists but pass/fail is not defined."""
        return self.has_mark and self.result_state is None


@dataclass(frozen=True)
class StudentAssessmentSource:
    """Raw assessment-plus-mark data before report calculations."""

    assessment: ReportAssessment
    mark_id: int | None
    mark_obtained: Decimal | None
    captured_at: str | None
    notes: str | None

    @property
    def has_mark(self) -> bool:
        """Return True when a mark row exists, including a recorded zero."""
        return self.mark_id is not None


@dataclass(frozen=True)
class ReportMarkSource:
    """Raw mark data with student context before report calculations."""

    student: ReportStudent
    mark_id: int
    assessment_id: int
    mark_obtained: Decimal
    captured_at: str
    notes: str | None


@dataclass(frozen=True)
class AssessmentPerformanceStudentRow:
    """One student's row in an assessment performance report."""

    student: ReportStudent
    mark_id: int | None
    mark_obtained: Decimal | None
    percentage: Decimal | None
    result_state: str | None
    captured_at: str | None
    notes: str | None
    is_currently_eligible: bool

    @property
    def has_mark(self) -> bool:
        """Return True when a mark row exists, including a recorded zero."""
        return self.mark_id is not None

    @property
    def is_missing(self) -> bool:
        """Return True when no mark row has been recorded."""
        return self.mark_id is None

    @property
    def is_unclassified(self) -> bool:
        """Return True when a mark exists but pass/fail is not defined."""
        return self.has_mark and self.result_state is None


@dataclass(frozen=True)
class PerformanceSummary:
    """Assessment performance totals calculated with Decimal percentages."""

    assessment_count: int
    expected_result_count: int
    recorded_result_count: int
    missing_result_count: int
    average_percentage: Decimal | None
    highest_percentage: Decimal | None
    lowest_percentage: Decimal | None
    pass_count: int | None
    fail_count: int | None
    unclassified_count: int

    @property
    def has_results(self) -> bool:
        """Return True when at least one mark has been recorded."""
        return self.recorded_result_count > 0

    @property
    def has_classified_results(self) -> bool:
        """Return True when any result had an assessment-specific pass mark."""
        return self.pass_count is not None and self.fail_count is not None


@dataclass(frozen=True)
class SystemOverviewReport:
    """Top-level system counts for the terminal dashboard."""

    student_count: int
    active_student_count: int
    inactive_student_count: int
    archived_student_count: int
    course_count: int
    planned_course_count: int
    active_course_count: int
    completed_course_count: int
    archived_course_count: int
    trainer_count: int
    active_trainer_count: int
    inactive_trainer_count: int
    archived_trainer_count: int
    enrolment_count: int
    active_enrolment_count: int
    completed_enrolment_count: int
    cancelled_enrolment_count: int
    trainer_assignment_count: int
    active_trainer_assignment_count: int
    ended_trainer_assignment_count: int
    attendance_session_count: int
    attendance_record_count: int
    assessment_count: int
    active_assessment_count: int
    archived_assessment_count: int
    mark_count: int


@dataclass(frozen=True)
class StudentProgressReport:
    """Progress report for one student."""

    student: ReportStudent
    enrolments: tuple[ReportEnrolmentRow, ...]
    overall_attendance: AttendanceStatusSummary
    course_attendance: tuple[CourseAttendanceSummaryRow, ...]
    assessment_results: tuple[StudentAssessmentReportRow, ...]


@dataclass(frozen=True)
class CourseOverviewReport:
    """Overview report for one course."""

    course: ReportCourse
    modules: tuple[ReportModule, ...]
    enrolments: tuple[ReportEnrolmentRow, ...]
    active_enrolment_count: int
    historical_enrolment_count: int
    trainer_assignments: tuple[ReportTrainerAssignmentRow, ...]
    active_trainer_assignment_count: int
    historical_trainer_assignment_count: int
    attendance_summary: AttendanceStatusSummary
    assessments: tuple[ReportAssessment, ...]
    performance_summary: PerformanceSummary


@dataclass(frozen=True)
class CourseAttendanceReport:
    """Attendance report for one course."""

    course: ReportCourse
    date_from: str | None
    date_to: str | None
    summary: AttendanceStatusSummary
    student_summaries: tuple[CourseAttendanceStudentRow, ...]
    sessions: tuple[AttendanceSessionReportRow, ...]


@dataclass(frozen=True)
class LowAttendanceReportRow:
    """One student in a low-attendance report."""

    student: ReportStudent
    course: ReportCourse
    summary: AttendanceStatusSummary


@dataclass(frozen=True)
class LowAttendanceReport:
    """Students below a threshold plus students without calculable attendance."""

    course: ReportCourse
    threshold_percentage: float
    students_below_threshold: tuple[LowAttendanceReportRow, ...]
    students_without_calculable_attendance: tuple[LowAttendanceReportRow, ...]


@dataclass(frozen=True)
class AssessmentPerformanceReport:
    """Performance report for one assessment."""

    assessment: ReportAssessment
    students: tuple[AssessmentPerformanceStudentRow, ...]
    summary: PerformanceSummary


@dataclass(frozen=True)
class TrainerAssignmentReport:
    """Course-assignment workload report for one trainer."""

    trainer: ReportTrainer
    active_assignments: tuple[ReportTrainerAssignmentRow, ...]
    ended_assignments: tuple[ReportTrainerAssignmentRow, ...]
