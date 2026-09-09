"""Reports and Statistics command-line screens."""

from dataclasses import dataclass
from decimal import Decimal

from ..config.settings import AppConfig
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
    ReportEnrolmentRow,
    ReportModule,
    ReportTrainerAssignmentRow,
    StudentAssessmentReportRow,
    StudentProgressReport,
    SystemOverviewReport,
    TrainerAssignmentReport,
)
from ..services.assessment_service import round_percentage_for_display
from ..services.report_service import ReportService
from ..utils.exceptions import DatabaseError, RecordNotFoundError, ValidationError
from .prompts import (
    is_cancel,
    is_valid_menu_choice,
    prompt_optional,
    prompt_required,
    read_menu_choice,
    read_text,
)
from .tables import format_status, format_title


DEFAULT_LOW_ATTENDANCE_THRESHOLD = "80"


@dataclass(frozen=True)
class ReportMenuOption:
    """A numbered Reports and Statistics menu option."""

    choice: str
    label: str


REPORT_MENU_OPTIONS = (
    ReportMenuOption("1", "System Overview"),
    ReportMenuOption("2", "Student Progress Report"),
    ReportMenuOption("3", "Course Overview Report"),
    ReportMenuOption("4", "Attendance Report"),
    ReportMenuOption("5", "Low Attendance Students"),
    ReportMenuOption("6", "Assessment Performance Report"),
    ReportMenuOption("7", "Trainer Assignment Report"),
    ReportMenuOption("0", "Back"),
)

VALID_REPORT_MENU_CHOICES = tuple(option.choice for option in REPORT_MENU_OPTIONS)


def run_report_menu(
    config: AppConfig,
    input_func=input,
    output_func=print,
    report_service: ReportService | None = None,
) -> None:
    """Run the Reports and Statistics submenu."""
    reports = report_service or ReportService(config.paths.database_path)

    while True:
        show_report_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_REPORT_MENU_CHOICES):
            output_func("Choose a number from the Reports and Statistics menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Main Menu.")
            output_func("")
            return

        if choice == "1":
            show_system_overview_report(reports, output_func)
        if choice == "1":
            show_student_progress_report(reports, input_func, output_func)
        elif choice == "3":
            show_course_overview_report(reports, input_func, output_func)
        elif choice == "4":
            show_course_attendance_report(reports, input_func, output_func)
        elif choice == "5":
            show_low_attendance_report(reports, input_func, output_func)
        elif choice == "6":
            show_assessment_performance_report(reports, input_func, output_func)
        elif choice == "7":
            show_trainer_assignment_report(reports, input_func, output_func)


def show_report_menu(output_func=print) -> None:
    """Display the Reports and Statistics submenu."""
    for line in format_title("REPORTS & STATISTICS"):
        output_func(line)

    for option in REPORT_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def show_system_overview_report(
    service: ReportService,
    output_func=print,
) -> None:
    """Display the system overview report."""
    output_func("")
    try:
        report = service.get_system_overview()
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_system_overview_report(report):
            output_func(line)

    output_func("")


def show_student_progress_report(
    service: ReportService,
    input_func=input,
    output_func=print,
) -> None:
    """Display one student's progress report."""
    output_func("")
    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Student progress report cancelled.")
        output_func("")
        return

    try:
        report = service.get_student_progress(student_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_student_progress_report(report):
            output_func(line)

    output_func("")


def show_course_overview_report(
    service: ReportService,
    input_func=input,
    output_func=print,
) -> None:
    """Display one course overview report."""
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Course overview report cancelled.")
        output_func("")
        return

    try:
        report = service.get_course_overview(course_code)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_course_overview_report(report):
            output_func(line)

    output_func("")


def show_course_attendance_report(
    service: ReportService,
    input_func=input,
    output_func=print,
) -> None:
    """Display one course attendance report."""
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Attendance report cancelled.")
        output_func("")
        return

    date_from = _prompt_optional("Date from [YYYY-MM-DD] (optional): ", input_func)
    if date_from == "q":
        output_func("Attendance report cancelled.")
        output_func("")
        return

    date_to = _prompt_optional("Date to [YYYY-MM-DD] (optional): ", input_func)
    if date_to == "q":
        output_func("Attendance report cancelled.")
        output_func("")
        return

    try:
        report = service.get_course_attendance_report(
            course_code,
            date_from=date_from,
            date_to=date_to,
        )
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_course_attendance_report(report):
            output_func(line)

    output_func("")


def show_low_attendance_report(
    service: ReportService,
    input_func=input,
    output_func=print,
) -> None:
    """Display low-attendance students for a course."""
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Low attendance report cancelled.")
        output_func("")
        return

    threshold = _prompt_optional(
        f"Threshold percentage [{DEFAULT_LOW_ATTENDANCE_THRESHOLD}]: ",
        input_func,
    )
    if threshold == "q":
        output_func("Low attendance report cancelled.")
        output_func("")
        return
    threshold = threshold or DEFAULT_LOW_ATTENDANCE_THRESHOLD

    try:
        report = service.get_low_attendance_students(course_code, threshold)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_low_attendance_report(report):
            output_func(line)

    output_func("")


def show_assessment_performance_report(
    service: ReportService,
    input_func=input,
    output_func=print,
) -> None:
    """Display one assessment performance report."""
    output_func("")
    assessment_id = _prompt_required("Enter assessment ID: ", input_func, output_func)
    if assessment_id is None:
        output_func("Assessment performance report cancelled.")
        output_func("")
        return

    try:
        report = service.get_assessment_performance(assessment_id)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_assessment_performance_report(report):
            output_func(line)

    output_func("")


def show_trainer_assignment_report(
    service: ReportService,
    input_func=input,
    output_func=print,
) -> None:
    """Display one trainer assignment report."""
    output_func("")
    trainer_number = _prompt_required("Enter trainer number: ", input_func, output_func)
    if trainer_number is None:
        output_func("Trainer assignment report cancelled.")
        output_func("")
        return

    try:
        report = service.get_trainer_assignment_report(trainer_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_trainer_assignment_report(report):
            output_func(line)

    output_func("")


def format_system_overview_report(report: SystemOverviewReport) -> list[str]:
    """Return a printable system overview report."""
    lines = format_title("System Overview")
    lines.extend(
        [
            f"{'Students':<30}: {report.student_count},
            f"{'Active students':<30}: {report.active_student_count}",
            f"{'Inactive students':<30}: {report.inactive_student_count}",
            f"{'Archived students':<30}: {report.archived_student_count}",
            f"{'Courses':<30}: {report.course_count}",
            f"{'Planned courses':<30}: {report.planned_course_count}",
            f"{'Active courses':<30}: {report.active_course_count}",
            f"{'Completed courses':<30}: {report.completed_course_count}",
            f"{'Archived courses':<30}: {report.archived_course_count}",
            f"{'Trainers':<30}: {report.trainer_count}",
            f"{'Active trainers':<30}: {report.active_trainer_count}",
            f"{'Inactive trainers':<30}: {report.inactive_trainer_count}",
            f"{'Archived trainers':<30}: {report.archived_trainer_count}",
            f"{'Enrolments':<30}: {report.enrolment_count}",
            f"{'Active enrolments':<30}: {report.active_enrolment_count}",
            f"{'Completed enrolments':<30}: {report.completed_enrolment_count}",
            f"{'Cancelled enrolments':<30}: {report.cancelled_enrolment_count}",
            f"{'Trainer assignments':<30}: {report.trainer_assignment_count}",
            f"{'Active trainer assignments':<30}: {report.active_trainer_assignment_count}",
            f"{'Ended trainer assignments':<30}: {report.ended_trainer_assignment_count}",
            f"{'Attendance sessions':<30}: {report.attendance_session_count}",
            f"{'Attendance records':<30}: {report.attendance_record_count}",
            f"{'Assessments':<30}: {report.assessment_count}",
            f"{'Active assessments':<30}: {report.active_assessment_count}",
            f"{'Archived assessments':<30}: {report.archived_assessment_count}",
            f"{'Marks':<30}: {report.mark_count}",
        ]
    )
    return lines


def format_student_progress_report(report: StudentProgressReport) -> list[str]:
    """Return a printable student progress report."""
    student = report.student
    lines = format_title("Student Progress Report")
    lines.extend(
        [
            f"{'Student':<22}: {student.student_number} {student.full_name}",
            f"{'Status':<22}: {format_status(student.status)}",
            "",
            "Enrolments",
        ]
    )
    lines.extend(_format_enrolment_rows(report.enrolments, show_student=False))
    lines.extend(["", "Attendance"])
    lines.extend(_format_attendance_summary(report.overall_attendance))
    lines.extend(["", "Course Attendance"])
    lines.extend(_format_course_attendance_rows(report.course_attendance))
    lines.extend(["", "Assessment Results"])
    lines.extend(_format_student_assessment_rows(report.assessment_results))
    return lines


def format_course_overview_report(report: CourseOverviewReport) -> list[str]:
    """Return a printable course overview report."""
    course = report.course
    lines = format_title("Course Overview Report")
    lines.extend(
        [
            f"{'Course':<28}: {course.course_code} - {course.course_name}",
            f"{'Status':<28}: {format_status(course.status)}",
            f"{'Active enrolments':<28}: {report.active_enrolment_count}",
            f"{'Historical enrolments':<28}: {report.historical_enrolment_count}",
            f"{'Active trainer assignments':<28}: {report.active_trainer_assignment_count}",
            f"{'Historical trainer assignments':<28}: {report.historical_trainer_assignment_count}",
            "",
            "Modules",
        ]
    )
    lines.extend(_format_module_rows(report.modules))
    lines.extend(["", "Enrolments"])
    lines.extend(_format_enrolment_rows(report.enrolments, show_student=True))
    lines.extend(["", "Trainer Assignments"])
    lines.extend(_format_assignment_rows(report.trainer_assignments, show_trainer=True))
    lines.extend(["", "Attendance Summary"])
    lines.extend(_format_attendance_summary(report.attendance_summary))
    lines.extend(["", "Assessments"])
    lines.extend(_format_assessment_rows(report.assessments))
    lines.extend(["", "Assessment Performance"])
    lines.extend(_format_performance_summary(report.performance_summary))
    return lines


def format_course_attendance_report(report: CourseAttendanceReport) -> list[str]:
    """Return a printable course attendance report."""
    course = report.course
    lines = format_title("Attendance Report")
    lines.extend(
        [
            f"{'Course':<22}: {course.course_code} - {course.course_name}",
            f"{'Date from':<22}: {report.date_from or 'No start date'}",
            f"{'Date to':<22}: {report.date_to or 'No end date'}",
            "",
            "Summary",
        ]
    )
    lines.extend(_format_attendance_summary(report.summary))
    lines.extend(["", "Students"])
    lines.extend(_format_attendance_student_rows(report.student_summaries))
    lines.extend(["", "Sessions"])
    lines.extend(_format_attendance_session_rows(report.sessions))
    return lines


def format_low_attendance_report(report: LowAttendanceReport) -> list[str]:
    """Return a printable low-attendance report."""
    lines = format_title("Low Attendance Students")
    lines.extend(
        [
            f"{'Course':<22}: {report.course.course_code} - {report.course.course_name}",
            f"{'Threshold':<22}: {report.threshold_percentage:.2f}%",
            "",
            "Below Threshold",
        ]
    )
    lines.extend(_format_low_attendance_rows(report.students_below_threshold))
    lines.extend(["", "No Calculable Attendance"])
    lines.extend(
        _format_low_attendance_rows(
            report.students_without_calculable_attendance,
            empty_message="No students without calculable attendance.",
        )
    )
    return lines


def format_assessment_performance_report(
    report: AssessmentPerformanceReport,
) -> list[str]:
    """Return a printable assessment performance report."""
    assessment = report.assessment
    lines = format_title("Assessment Performance Report")
    lines.extend(_format_assessment_detail(assessment))
    lines.extend(["", "Summary"])
    lines.extend(_format_performance_summary(report.summary))
    lines.extend(["", "Students"])
    lines.extend(_format_assessment_performance_rows(report.students))
    return lines


def format_trainer_assignment_report(report: TrainerAssignmentReport) -> list[str]:
    """Return a printable trainer assignment report."""
    trainer = report.trainer
    lines = format_title("Trainer Assignment Report")
    lines.extend(
        [
            f"{'Trainer':<22}: {trainer.trainer_number} {trainer.full_name}",
            f"{'Status':<22}: {format_status(trainer.status)}",
            "",
            "Active Course Assignments",
        ]
    )
    lines.extend(_format_assignment_rows(report.active_assignments))
    lines.extend(["", "Historical Course Assignments"])
    lines.extend(
        _format_assignment_rows(
            report.ended_assignments,
            empty_message="No historical course assignments found.",
        )
    )
    return lines


def _format_enrolment_rows(
    enrolments: tuple[ReportEnrolmentRow, ...],
    show_student: bool,
) -> list[str]:
    if not enrolments:
        return ["No enrolments recorded."]

    if show_student:
        lines = [
            f"{'Student':<30} {'Date':<10} {'Status':<10} Course",
            "-" * 86,
        ]
        for enrolment in enrolments:
            lines.append(
                f"{enrolment.student_number + ' ' + enrolment.student_name:<30} "
                f"{enrolment.enrolment_date:<10} "
                f"{format_status(enrolment.status):<10} "
                f"{enrolment.course_code}"
            )
        return lines

    lines = [
        f"{'Course':<14} {'Date':<10} {'Status':<10} Details",
        "-" * 76,
    ]
    for enrolment in enrolments:
        detail = "-"
        if enrolment.cancelled_at is not None:
            detail = f"Cancelled {enrolment.cancelled_at}: {enrolment.cancellation_reason}"
        lines.append(
            f"{enrolment.course_code:<14} "
            f"{enrolment.enrolment_date:<10} "
            f"{format_status(enrolment.status):<10} "
            f"{detail}"
        )
    return lines


def _format_module_rows(modules: tuple[ReportModule, ...]) -> list[str]:
    if not modules:
        return ["No modules recorded for this course."]

    lines = [
        f"{'Seq':<4} {'Code':<14} {'Status':<10} Name",
        "-" * 72,
    ]
    for module in modules:
        lines.append(
            f"{module.sequence_number:<4} "
            f"{module.module_code:<14} "
            f"{format_status(module.status):<10} "
            f"{module.module_name}"
        )
    return lines


def _format_assignment_rows(
    assignments: tuple[ReportTrainerAssignmentRow, ...],
    show_trainer: bool = False,
    empty_message: str = "No course assignments found.",
) -> list[str]:
    if not assignments:
        return [empty_message]

    first_column = "Trainer" if show_trainer else "Course"
    lines = [
        f"{first_column:<30} {'From':<10} {'To':<10} {'Status'}",
        "-" * 72,
    ]
    for assignment in assignments:
        label = (
            f"{assignment.trainer_number} {assignment.trainer_name}"
            if show_trainer
            else f"{assignment.course_code} - {assignment.course_name}"
        )
        lines.append(
            f"{label:<30} "
            f"{assignment.assigned_from:<10} "
            f"{assignment.assigned_to or '-':<10} "
            f"{format_status(assignment.status)}"
        )
    return lines


def _format_course_attendance_rows(
    rows: tuple[CourseAttendanceSummaryRow, ...],
) -> list[str]:
    if not rows:
        return ["No course attendance summaries available."]

    lines = [
        f"{'Course':<14} {'Records':<8} {'Attended':<8} {'Eligible':<8} Percentage",
        "-" * 76,
    ]
    for row in rows:
        summary = row.summary
        lines.append(
            f"{row.course.course_code:<14} "
            f"{summary.record_count:<8} "
            f"{summary.attended_count:<8} "
            f"{summary.percentage_denominator:<8} "
            f"{_format_attendance_percentage(summary)}"
        )
    return lines


def _format_attendance_summary(summary: AttendanceStatusSummary) -> list[str]:
    return [
        f"{'Sessions':<22}: {summary.session_count}",
        f"{'Records':<22}: {summary.record_count}",
        f"{'Present':<22}: {summary.present_count}",
        f"{'Late':<22}: {summary.late_count}",
        f"{'Absent':<22}: {summary.absent_count}",
        f"{'Excused':<22}: {summary.excused_count}",
        f"{'Unknown':<22}: {summary.unknown_count}",
        f"{'Eligible records':<22}: {summary.percentage_denominator}",
        f"{'Attendance percentage':<22}: {_format_attendance_percentage(summary)}",
    ]


def _format_attendance_session_rows(
    sessions: tuple[AttendanceSessionReportRow, ...],
) -> list[str]:
    if not sessions:
        return ["No attendance sessions found for this course."]

    lines = [
        f"{'ID':<5} {'Date':<10} {'Topic':<22} {'Records':<8} {'Attended':<8} Percentage",
        "-" * 92,
    ]
    for session in sessions:
        lines.append(
            f"{session.session_id:<5} "
            f"{session.session_date:<10} "
            f"{_format_topic(session.topic):<22} "
            f"{session.record_count:<8} "
            f"{session.attended_count:<8} "
            f"{_format_optional_attendance_percentage(session.attendance_percentage)}"
        )
    return lines


def _format_attendance_student_rows(
    rows: tuple[CourseAttendanceStudentRow, ...],
) -> list[str]:
    if not rows:
        return ["No students found for this course."]

    lines = [
        f"{'Student':<30} {'Records':<8} {'Present':<8} {'Late':<6} {'Absent':<7} Percentage",
        "-" * 92,
    ]
    for row in rows:
        summary = row.summary
        lines.append(
            f"{row.student.student_number + ' ' + row.student.full_name:<30} "
            f"{summary.record_count:<8} "
            f"{summary.present_count:<8} "
            f"{summary.late_count:<6} "
            f"{summary.absent_count:<7} "
            f"{_format_attendance_percentage(summary)}"
        )
    return lines


def _format_low_attendance_rows(
    rows: tuple[LowAttendanceReportRow, ...],
    empty_message: str = "No students are below this threshold.",
) -> list[str]:
    if not rows:
        return [empty_message]

    lines = [
        f"{'Student':<30} {'Records':<8} {'Attended':<8} {'Eligible':<8} Percentage",
        "-" * 86,
    ]
    for row in rows:
        summary = row.summary
        lines.append(
            f"{row.student.student_number + ' ' + row.student.full_name:<30} "
            f"{summary.record_count:<8} "
            f"{summary.attended_count:<8} "
            f"{summary.percentage_denominator:<8} "
            f"{_format_attendance_percentage(summary)}"
        )
    return lines


def _format_assessment_rows(
    assessments: tuple[ReportAssessment, ...],
) -> list[str]:
    if not assessments:
        return ["No assessments recorded for this course."]

    lines = [
        f"{'ID':<5} {'Module':<18} {'Type':<10} {'Max':<8} {'Pass':<8} {'Status':<9} Name",
        "-" * 106,
    ]
    for assessment in assessments:
        lines.append(
            f"{assessment.assessment_id:<5} "
            f"{assessment.module_label:<18} "
            f"{assessment.assessment_type:<10} "
            f"{_format_decimal(assessment.max_mark):<8} "
            f"{_format_optional_decimal(assessment.pass_mark):<8} "
            f"{format_status(assessment.status):<9} "
            f"{assessment.assessment_name}"
        )
    return lines


def _format_student_assessment_rows(
    rows: tuple[StudentAssessmentReportRow, ...],
) -> list[str]:
    if not rows:
        return ["No assessment results available."]

    lines = [
        f"{'Course':<12} {'Assessment':<24} {'Score':<13} {'Percent':<10} {'Result':<12} Status",
        "-" * 104,
    ]
    for row in rows:
        assessment = row.assessment
        lines.append(
            f"{assessment.course_code:<12} "
            f"{assessment.assessment_name:<24} "
            f"{_format_score(row.mark_obtained, assessment.max_mark):<13} "
            f"{_format_optional_decimal_percentage(row.percentage):<10} "
            f"{_format_result_state(row.result_state):<12} "
            f"{_format_mark_status(row)}"
        )
    return lines


def _format_assessment_performance_rows(
    rows: tuple[AssessmentPerformanceStudentRow, ...],
) -> list[str]:
    if not rows:
        return ["No eligible students or recorded marks found for this assessment."]

    lines = [
        f"{'Student':<30} {'Eligibility':<12} {'Score':<13} {'Percent':<10} Result",
        "-" * 88,
    ]
    for row in rows:
        lines.append(
            f"{row.student.student_number + ' ' + row.student.full_name:<30} "
            f"{_format_eligibility(row):<12} "
            f"{_format_mark_only(row.mark_obtained):<13} "
            f"{_format_optional_decimal_percentage(row.percentage):<10} "
            f"{_format_result_state(row.result_state)}"
        )
    return lines


def _format_performance_summary(summary: PerformanceSummary) -> list[str]:
    lines = [
        f"{'Assessments':<24}: {summary.assessment_count}",
        f"{'Eligible result rows':<24}: {summary.expected_result_count}",
        f"{'Recorded marks':<24}: {summary.recorded_result_count}",
        f"{'Missing marks':<24}: {summary.missing_result_count}",
        f"{'Average percentage':<24}: {_format_optional_decimal_percentage(summary.average_percentage)}",
        f"{'Highest percentage':<24}: {_format_optional_decimal_percentage(summary.highest_percentage)}",
        f"{'Lowest percentage':<24}: {_format_optional_decimal_percentage(summary.lowest_percentage)}",
        f"{'Unclassified marks':<24}: {summary.unclassified_count}",
    ]
    if summary.has_classified_results:
        lines.extend(
            [
                f"{'Pass count':<24}: {summary.pass_count}",
                f"{'Fail count':<24}: {summary.fail_count}",
            ]
        )
    else:
        lines.append(f"{'Pass/fail':<24}: Not defined")

    return lines


def _format_assessment_detail(assessment: ReportAssessment) -> list[str]:
    return [
        f"{'Assessment ID':<22}: {assessment.assessment_id}",
        f"{'Assessment':<22}: {assessment.assessment_name}",
        f"{'Type':<22}: {assessment.assessment_type}",
        f"{'Course':<22}: {assessment.course_code} - {assessment.course_name}",
        f"{'Module':<22}: {assessment.module_label}",
        f"{'Maximum mark':<22}: {_format_decimal(assessment.max_mark)}",
        f"{'Pass mark':<22}: {_format_optional_decimal(assessment.pass_mark)}",
        f"{'Status':<22}: {format_status(assessment.status)}",
    ]


def _format_attendance_percentage(summary: AttendanceStatusSummary) -> str:
    return _format_optional_attendance_percentage(summary.attendance_percentage)


def _format_optional_attendance_percentage(value: float | None) -> str:
    if value is None:
        return "No calculable attendance"

    return f"{value:.2f}%"


def _format_score(value: Decimal | None, max_mark: Decimal) -> str:
    if value is None:
        return f"0/{_format_decimal(max_mark)}"

    return f"{_format_decimal(value)}/{_format_decimal(max_mark)}"


def _format_mark_only(value: Decimal | None) -> str:
    if value is None:
        return "0"

    return _format_decimal(value)


def _format_mark_status(row: StudentAssessmentReportRow) -> str:
    if row.is_missing:
        return "Missing"
    if row.is_unclassified:
        return "Recorded; pass/fail not defined"

    return "Recorded"


def _format_eligibility(row: AssessmentPerformanceStudentRow) -> str:
    if row.is_currently_eligible:
        return "Eligible"

    return "Historical"


def _format_optional_decimal_percentage(value: Decimal | None) -> str:
    if value is None:
        return "No results"

    rounded = round_percentage_for_display(value)
    return f"{rounded:.2f}%"


def _format_result_state(result_state: str | None) -> str:
    if result_state is None:
        return "Not defined"

    return format_status(result_state)


def _format_optional_decimal(value: Decimal | None) -> str:
    if value is None:
        return "0"

    return _format_decimal(value)


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _format_topic(topic: str) -> str:
    return topic or "-"


def _prompt_required(prompt: str, input_func, output_func) -> str | None:
    return prompt_required(prompt, input_func, output_func)


def _prompt_optional(prompt: str, input_func) -> str | None:
    return prompt_optional(prompt, input_func)


def _read_text(prompt: str, input_func) -> str:
    return read_text(prompt, input_func)


def _is_cancel(value: str) -> bool:
    return is_cancel(value)
