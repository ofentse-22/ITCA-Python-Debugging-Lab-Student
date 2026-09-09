"""Business rules for reports and statistics."""

from decimal import Decimal
from pathlib import Path
import logging

from ..models.attendance_record import (
    ATTENDANCE_ABSENT_STATUS,
    ATTENDANCE_EXCUSED_STATUS,
    ATTENDANCE_LATE_STATUS,
    ATTENDANCE_PRESENT_STATUS,
    ATTENDANCE_UNKNOWN_STATUS,
    calculate_attendance_percentage,
)
from ..models.mark import RESULT_FAIL_STATE, RESULT_PASS_STATE
from ..models.reports import (
    AssessmentPerformanceReport,
    AssessmentPerformanceStudentRow,
    AttendanceSessionReportRow,
    AttendanceStatusSummary,
    CourseAttendanceReport,
    CourseAttendanceStudentRow,
    CourseAttendanceSummaryRow,
    CourseOverviewReport,
    LowAttendanceReport,
    LowAttendanceReportRow,
    PerformanceSummary,
    ReportAssessment,
    ReportAttendanceRecordSource,
    ReportAttendanceSessionSource,
    ReportCourse,
    ReportMarkSource,
    ReportStudent,
    ReportTrainerAssignmentRow,
    StudentAssessmentReportRow,
    StudentAssessmentSource,
    StudentProgressReport,
    SystemOverviewReport,
    TrainerAssignmentReport,
)
from ..repositories.report_repository import ReportRepository
from ..utils.exceptions import DatabaseError, RecordNotFoundError, ValidationError
from ..utils.logging_setup import get_application_logger
from ..utils.validators import (
    normalize_course_code,
    normalize_optional_iso_date,
    normalize_percentage_threshold,
    normalize_positive_integer,
    normalize_student_number,
    normalize_trainer_number,
)
from .assessment_service import calculate_percentage, calculate_result_state


class ReportService:
    """Read-only report workflow service."""

    def __init__(
        self,
        database_path: Path,
        repository: ReportRepository | None = None,
        logger: logging.Logger | None = None,
    ):
        self.repository = repository or ReportRepository(database_path)
        self.logger = logger or get_application_logger()

    def get_system_overview(self) -> SystemOverviewReport:
        """Return system-wide counts."""
        try:
            return self.repository.get_system_overview()
        except DatabaseError:
            self.logger.exception("System overview report failed")
            raise

    def get_student_progress(self, student_number: str) -> StudentProgressReport:
        """Return a progress report for one student."""
        normalized_number = normalize_student_number(student_number)
        try:
            student = self.repository.get_student_by_number(normalized_number)
            if student is None:
                raise RecordNotFoundError(
                    f"No student was found for number {normalized_number}."
                )

            enrolments = tuple(
                enrolment
                for enrolment in self.repository.list_student_enrolments(
                    student.student_id
                )
                if enrolment.status != "cancelled"
            )
            attendance_records = self.repository.list_attendance_records_for_student(
                student.student_id,
            )
            overall_attendance = _attendance_summary_from_records(attendance_records)
            course_attendance = self._course_attendance_for_student(student, enrolments)
            assessment_results = tuple(
                _student_assessment_row(source)
                for source in self.repository.list_student_assessment_sources(
                    student.student_id,
                )
            )

            return StudentProgressReport(
                student=student,
                enrolments=enrolments,
                overall_attendance=overall_attendance,
                course_attendance=course_attendance,
                assessment_results=assessment_results,
            )
        except DatabaseError:
            self.logger.exception("Student progress report failed")
            raise

    def get_course_overview(self, course_code: str) -> CourseOverviewReport:
        """Return an overview report for one course."""
        course = self._get_course(course_code)
        try:
            modules = tuple(self.repository.list_modules_for_course(course.course_id))
            enrolments = tuple(
                self.repository.list_course_enrolments(course.course_id)
            )
            assignments = tuple(
                self.repository.list_trainer_assignments_for_course(course.course_id)
            )
            session_sources = self.repository.list_attendance_sessions_for_course(
                course.course_id,
            )
            attendance_records = self.repository.list_attendance_records_for_course(
                course.course_id,
            )
            assessments = tuple(
                self.repository.list_assessments_for_course(course.course_id)
            )

            return CourseOverviewReport(
                course=course,
                modules=modules,
                enrolments=enrolments,
                active_enrolment_count=sum(
                    1 for enrolment in enrolments if enrolment.is_active
                ),
                historical_enrolment_count=sum(
                    1 for enrolment in enrolments if enrolment.is_historical
                ),
                trainer_assignments=assignments,
                active_trainer_assignment_count=sum(
                    1 for assignment in assignments if assignment.is_active
                ),
                historical_trainer_assignment_count=sum(
                    1 for assignment in assignments if assignment.is_historical
                ),
                attendance_summary=_attendance_summary_from_records(
                    attendance_records,
                    session_count=len(session_sources),
                ),
                assessments=assessments,
                performance_summary=self._course_performance_summary(assessments),
            )
        except DatabaseError:
            self.logger.exception("Course overview report failed")
            raise

    def get_course_attendance_report(
        self,
        course_code: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> CourseAttendanceReport:
        """Return attendance totals and session rows for one course."""
        course = self._get_course(course_code)
        normalized_from, normalized_to = _normalize_date_range(date_from, date_to)

        try:
            session_sources = self.repository.list_attendance_sessions_for_course(
                course.course_id,
                date_from=normalized_from,
                date_to=normalized_to,
            )
            attendance_records = self.repository.list_attendance_records_for_course(
                course.course_id,
                date_from=normalized_from,
                date_to=normalized_to,
            )
            enrolments = self.repository.list_course_enrolments(course.course_id)

            return CourseAttendanceReport(
                course=course,
                date_from=normalized_from,
                date_to=normalized_to,
                summary=_attendance_summary_from_records(
                    attendance_records,
                    session_count=len(session_sources),
                ),
                student_summaries=self._course_attendance_students(
                    course,
                    enrolments,
                    normalized_from,
                    normalized_to,
                ),
                sessions=tuple(
                    _attendance_session_row(source)
                    for source in session_sources
                ),
            )
        except DatabaseError:
            self.logger.exception("Course attendance report failed")
            raise

    def get_low_attendance_students(
        self,
        course_code: str,
        threshold_percentage: int | float | str,
    ) -> LowAttendanceReport:
        """Return active course students below a strict attendance threshold."""
        course = self._get_course(course_code)
        threshold = normalize_percentage_threshold(threshold_percentage)

        try:
            students = self.repository.list_active_students_for_course(course.course_id)
            below_threshold = []
            no_calculable_attendance = []

            for student in students:
                records = self.repository.list_attendance_records_for_student(
                    student.student_id,
                    course.course_id,
                )
                summary = _attendance_summary_from_records(records)
                row = LowAttendanceReportRow(
                    student=student,
                    course=course,
                    summary=summary,
                )
                if summary.attendance_percentage is None:
                    no_calculable_attendance.append(row)
                elif summary.attendance_percentage <= threshold:
                    below_threshold.append(row)

            return LowAttendanceReport(
                course=course,
                threshold_percentage=threshold,
                students_below_threshold=tuple(
                    sorted(
                        below_threshold,
                        key=_low_attendance_sort_key,
                    )
                ),
                students_without_calculable_attendance=tuple(
                    sorted(
                        no_calculable_attendance,
                        key=_student_row_sort_key,
                    )
                ),
            )
        except DatabaseError:
            self.logger.exception("Low attendance report failed")
            raise

    def get_assessment_performance(
        self,
        assessment_id: int | str,
    ) -> AssessmentPerformanceReport:
        """Return performance and missing-result data for one assessment."""
        normalized_id = normalize_positive_integer(assessment_id, "Assessment ID")
        try:
            assessment = self.repository.get_assessment_by_id(normalized_id)
            if assessment is None:
                raise RecordNotFoundError(
                    f"No assessment was found for ID {normalized_id}."
                )

            rows = self._assessment_performance_rows(assessment)
            return AssessmentPerformanceReport(
                assessment=assessment,
                students=rows,
                summary=_performance_summary(
                    assessments=(assessment,),
                    expected_result_count=sum(
                        1 for row in rows if row.is_currently_eligible
                    ),
                    missing_result_count=sum(
                        1
                        for row in rows
                        if row.is_currently_eligible and row.is_missing
                    ),
                    rows=rows,
                ),
            )
        except DatabaseError:
            self.logger.exception("Assessment performance report failed")
            raise

    def get_trainer_assignment_report(
        self,
        trainer_number: str,
    ) -> TrainerAssignmentReport:
        """Return course-assignment workload for one trainer."""
        normalized_number = normalize_trainer_number(trainer_number)
        try:
            trainer = self.repository.get_trainer_by_number(normalized_number)
            if trainer is None:
                raise RecordNotFoundError(
                    f"No trainer was found for number {normalized_number}."
                )

            assignments = self.repository.list_trainer_assignments_for_trainer(
                trainer.trainer_id,
            )
            return TrainerAssignmentReport(
                trainer=trainer,
                active_assignments=tuple(
                    assignment for assignment in assignments if assignment.is_active
                ),
                ended_assignments=tuple(
                    assignment for assignment in assignments if assignment.is_historical
                ),
            )
        except DatabaseError:
            self.logger.exception("Trainer assignment report failed")
            raise

    def _course_attendance_for_student(
        self,
        student: ReportStudent,
        enrolments,
    ) -> tuple[CourseAttendanceSummaryRow, ...]:
        course_rows: dict[int, ReportCourse] = {}
        for enrolment in enrolments:
            if enrolment.course_id in course_rows:
                continue
            course_rows[enrolment.course_id] = ReportCourse(
                course_id=enrolment.course_id,
                course_code=enrolment.course_code,
                course_name=enrolment.course_name,
                status=enrolment.course_status,
            )

        summaries = []
        for course_id, course in course_rows.items():
            records = self.repository.list_attendance_records_for_student(
                student.student_id,
                course_id,
            )
            summaries.append(
                CourseAttendanceSummaryRow(
                    course=course,
                    summary=_attendance_summary_from_records(records),
                )
            )

        return tuple(summaries)

    def _course_performance_summary(
        self,
        assessments: tuple[ReportAssessment, ...],
    ) -> PerformanceSummary:
        rows: list[AssessmentPerformanceStudentRow] = []
        expected_result_count = 0
        missing_result_count = 0

        for assessment in assessments:
            assessment_rows = self._assessment_performance_rows(assessment)
            rows.extend(assessment_rows)
            expected_result_count += sum(
                1 for row in assessment_rows if row.is_currently_eligible
            )
            missing_result_count += sum(
                1
                for row in assessment_rows
                if row.is_currently_eligible and row.is_missing
            )

        return _performance_summary(
            assessments=assessments,
            expected_result_count=expected_result_count,
            missing_result_count=missing_result_count,
            rows=tuple(rows),
        )

    def _assessment_performance_rows(
        self,
        assessment: ReportAssessment,
    ) -> tuple[AssessmentPerformanceStudentRow, ...]:
        students = self.repository.list_active_students_for_course(
            assessment.course_id,
        )
        marks = self.repository.list_marks_for_assessment(assessment.assessment_id)
        marks_by_student_id = {source.student.student_id: source for source in marks}
        active_student_ids = {student.student_id for student in students}

        rows = [
            _assessment_performance_row(
                assessment=assessment,
                student=student,
                mark_source=marks_by_student_id.get(student.student_id),
                is_currently_eligible=True,
            )
            for student in students
        ]
        rows.extend(
            _assessment_performance_row(
                assessment=assessment,
                student=source.student,
                mark_source=source,
                is_currently_eligible=False,
            )
            for source in marks
            if source.student.student_id not in active_student_ids
        )

        return tuple(rows)

    def _course_attendance_students(
        self,
        course: ReportCourse,
        enrolments,
        date_from: str | None,
        date_to: str | None,
    ) -> tuple[CourseAttendanceStudentRow, ...]:
        students: dict[int, ReportStudent] = {}
        for enrolment in enrolments:
            if enrolment.student_id in students:
                continue
            students[enrolment.student_id] = ReportStudent(
                student_id=enrolment.student_id,
                student_number=enrolment.student_number,
                first_name=enrolment.student_first_name,
                last_name=enrolment.student_last_name,
                status=enrolment.student_status,
            )

        rows = []
        for student in students.values():
            records = self.repository.list_attendance_records_for_student(
                student.student_id,
                course.course_id,
                date_from=date_from,
                date_to=date_to,
            )
            rows.append(
                CourseAttendanceStudentRow(
                    student=student,
                    summary=_attendance_summary_from_records(records),
                )
            )

        return tuple(rows)

    def _get_course(self, course_code: str) -> ReportCourse:
        normalized_code = normalize_course_code(course_code)
        try:
            course = self.repository.get_course_by_code(normalized_code)
        except DatabaseError:
            self.logger.exception("Report course lookup failed")
            raise

        if course is None:
            raise RecordNotFoundError(f"No course was found for code {normalized_code}.")

        return course


def _normalize_date_range(
    date_from: str | None,
    date_to: str | None,
) -> tuple[str | None, str | None]:
    normalized_from = normalize_optional_iso_date(date_from, "Date from")
    normalized_to = normalize_optional_iso_date(date_to, "Date to")
    if (
        normalized_from is not None
        and normalized_to is not None
        and normalized_from > normalized_to
        and normalized_to > normalized_from
    ):
        raise ValidationError("Date from may not be after date to.")

    return normalized_from, normalized_to


def _attendance_summary_from_records(
    records: list[ReportAttendanceRecordSource],
    session_count: int | None = None,
) -> AttendanceStatusSummary:
    present_count = _count_status(records, ATTENDANCE_PRESENT_STATUS)
    late_count = _count_status(records, ATTENDANCE_LATE_STATUS)
    absent_count = _count_status(records, ATTENDANCE_ABSENT_STATUS)
    excused_count = _count_status(records, ATTENDANCE_EXCUSED_STATUS)
    unknown_count = _count_status(records, ATTENDANCE_UNKNOWN_STATUS)
    denominator = present_count + late_count + absent_count

    return AttendanceStatusSummary(
        session_count=(
            len({record.session_id for record in records})
            if session_count is None
            else session_count
        ),
        record_count=len(records),
        present_count=present_count,
        late_count=late_count,
        absent_count=absent_count,
        excused_count=excused_count,
        unknown_count=unknown_count,
        percentage_denominator=denominator,
        attendance_percentage=calculate_attendance_percentage(
            present_count,
            late_count,
            absent_count,
        ),
    )


def _attendance_session_row(
    source: ReportAttendanceSessionSource,
) -> AttendanceSessionReportRow:
    denominator = source.present_count + source.late_count + source.absent_count
    return AttendanceSessionReportRow(
        session_id=source.session_id,
        session_date=source.session_date,
        topic=source.topic,
        record_count=source.record_count,
        present_count=source.present_count,
        late_count=source.late_count,
        absent_count=source.absent_count,
        excused_count=source.excused_count,
        unknown_count=source.unknown_count,
        percentage_denominator=denominator,
        attendance_percentage=calculate_attendance_percentage(
            source.present_count,
            source.late_count,
            source.absent_count,
        ),
    )


def _student_assessment_row(
    source: StudentAssessmentSource,
) -> StudentAssessmentReportRow:
    percentage = None
    result_state = None
    if source.has_mark and source.mark_obtained is not None:
        percentage = calculate_percentage(
            source.mark_obtained,
            source.assessment.max_mark,
        )
        result_state = calculate_result_state(
            source.mark_obtained,
            source.assessment.pass_mark,
        )

    return StudentAssessmentReportRow(
        assessment=source.assessment,
        mark_id=source.mark_id,
        mark_obtained=source.mark_obtained,
        percentage=percentage,
        result_state=result_state,
        captured_at=source.captured_at,
        notes=source.notes,
    )


def _assessment_performance_row(
    assessment: ReportAssessment,
    student: ReportStudent,
    mark_source: ReportMarkSource | None,
    is_currently_eligible: bool,
) -> AssessmentPerformanceStudentRow:
    if mark_source is None:
        return AssessmentPerformanceStudentRow(
            student=student,
            mark_id=None,
            mark_obtained=None,
            percentage=None,
            result_state=None,
            captured_at=None,
            notes=None,
            is_currently_eligible=is_currently_eligible,
        )

    percentage = calculate_percentage(mark_source.mark_obtained, assessment.max_mark)
    return AssessmentPerformanceStudentRow(
        student=student,
        mark_id=mark_source.mark_id,
        mark_obtained=mark_source.mark_obtained,
        percentage=percentage,
        result_state=calculate_result_state(
            mark_source.mark_obtained,
            assessment.pass_mark,
        ),
        captured_at=mark_source.captured_at,
        notes=mark_source.notes,
        is_currently_eligible=is_currently_eligible,
    )


def _performance_summary(
    assessments: tuple[ReportAssessment, ...],
    expected_result_count: int,
    missing_result_count: int,
    rows: tuple[AssessmentPerformanceStudentRow, ...],
) -> PerformanceSummary:
    result_rows = [row for row in rows if row.has_mark]
    percentages = [
        row.percentage
        for row in result_rows
        if row.percentage is not None
    ]

    average_percentage = None
    highest_percentage = None
    lowest_percentage = None
    if percentages:
        average_percentage = sum(percentages, Decimal("0")) // Decimal(len(percentages))
        highest_percentage = max(percentages)
        lowest_percentage = min(percentages)

    has_pass_mark = any(assessment.has_pass_mark for assessment in assessments)
    pass_count = None
    fail_count = None
    if has_pass_mark:
        pass_count = sum(1 for row in result_rows if row.result_state == RESULT_PASS_STATE)
        fail_count = sum(1 for row in result_rows if row.result_state == RESULT_FAIL_STATE)

    return PerformanceSummary(
        assessment_count=len(assessments),
        expected_result_count=expected_result_count,
        recorded_result_count=len(result_rows),
        missing_result_count=missing_result_count,
        average_percentage=average_percentage,
        highest_percentage=highest_percentage,
        lowest_percentage=lowest_percentage,
        pass_count=pass_count,
        fail_count=fail_count,
        unclassified_count=sum(1 for row in result_rows if row.result_state is None),
    )


def _count_status(
    records: list[ReportAttendanceRecordSource],
    status: str,
    counts: dict[str, int] = {},
) -> int:
    if status not in counts:
        counts[status] = sum(1 for record in records if record.status == status)
    return counts[status]


def _low_attendance_sort_key(row: LowAttendanceReportRow):
    return (
        row.summary.attendance_percentage,
        row.student.last_name.lower(),
        row.student.first_name.lower(),
        row.student.student_number.lower(),
    )


def _student_row_sort_key(row: LowAttendanceReportRow):
    return (
        row.student.last_name.lower(),
        row.student.first_name.lower(),
        row.student.student_number.lower(),
    )


def _assessment_row_sort_key(row: AssessmentPerformanceStudentRow):
    return (
        row.student.last_name.lower(),
        row.student.first_name.lower(),
        row.student.student_number.lower(),
    )
