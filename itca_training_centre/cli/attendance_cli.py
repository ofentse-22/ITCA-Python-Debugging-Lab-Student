"""Attendance Management command-line screens."""

from dataclasses import dataclass

from ..config.settings import AppConfig
from ..models.attendance_record import (
    ATTENDANCE_STATUSES,
    ATTENDANCE_UNKNOWN_STATUS,
    AttendanceRecord,
    AttendanceRegisterEntry,
    AttendanceSummary,
)
from ..models.attendance_session import AttendanceSession
from ..models.course import Course
from ..models.student import Student
from ..services.attendance_service import AttendanceService
from ..services.course_service import CourseService
from ..services.student_service import StudentService
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from .prompts import (
    confirm,
    is_cancel,
    is_valid_menu_choice,
    prompt_optional,
    prompt_required,
    prompt_yes_no,
    read_menu_choice,
    read_text,
)
from .tables import format_status, format_title


DEFAULT_LOW_ATTENDANCE_THRESHOLD = "80"


@dataclass(frozen=True)
class AttendanceMenuOption:
    """A numbered Attendance Management menu option."""

    choice: str
    label: str


ATTENDANCE_MENU_OPTIONS = (
    AttendanceMenuOption("1", "Create Attendance Session"),
    AttendanceMenuOption("2", "View Attendance Session"),
    AttendanceMenuOption("3", "List / Search Sessions"),
    AttendanceMenuOption("4", "Record Class Attendance"),
    AttendanceMenuOption("5", "Record Individual Attendance"),
    AttendanceMenuOption("6", "Update Attendance Record"),
    AttendanceMenuOption("7", "View Session Register"),
    AttendanceMenuOption("8", "View Student Attendance"),
    AttendanceMenuOption("9", "Attendance Summary"),
    AttendanceMenuOption("0", "Back"),
)

VALID_ATTENDANCE_MENU_CHOICES = tuple(option.choice for option in ATTENDANCE_MENU_OPTIONS)


def run_attendance_menu(
    config: AppConfig,
    input_func=input,
    output_func=print,
    attendance_service: AttendanceService | None = None,
    course_service: CourseService | None = None,
    student_service: StudentService | None = None,
) -> None:
    """Run the Attendance Management submenu."""
    attendance = attendance_service or AttendanceService(config.paths.database_path)
    courses = course_service or CourseService(config.paths.database_path)
    students = student_service or StudentService(config.paths.database_path)

    while True:
        show_attendance_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_ATTENDANCE_MENU_CHOICES):
            output_func("Choose a number from the Attendance Management menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Main Menu.")
            output_func("")
            return

        if choice == "1":
            create_attendance_session(attendance, input_func, output_func)
        elif choice == "2":
            view_attendance_session(attendance, courses, input_func, output_func)
        elif choice == "3":
            list_attendance_sessions(attendance, courses, input_func, output_func)
        elif choice == "4":
            record_class_attendance(attendance, courses, input_func, output_func)
        elif choice == "5":
            record_individual_attendance(attendance, courses, input_func, output_func)
        elif choice == "6":
            update_attendance_record(attendance, courses, input_func, output_func)
        elif choice == "7":
            view_session_register(attendance, students, courses, input_func, output_func)
        elif choice == "8":
            view_student_attendance(attendance, courses, input_func, output_func)
        elif choice == "9":
            attendance_summary(attendance, courses, students, input_func, output_func)


def show_attendance_menu(output_func=print) -> None:
    """Display the Attendance Management submenu."""
    for line in format_title("Attendance Management"):
        output_func(line)

    for option in ATTENDANCE_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def create_attendance_session(
    service: AttendanceService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    for line in format_title("Create Attendance Session"):
        output_func(line)
    output_func("Enter q at any prompt to cancel.")

    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Attendance session creation cancelled.")
        output_func("")
        return

    session_date = _prompt_required(
        "Enter session date [YYYY-MM-DD]: ",
        input_func,
        output_func,
    )
    if session_date is None:
        output_func("Attendance session creation cancelled.")
        output_func("")
        return

    topic = _prompt_optional("Enter topic (optional): ", input_func)
    if topic == "q":
        output_func("Attendance session creation cancelled.")
        output_func("")
        return

    try:
        session = service.create_session(
            course_code=course_code,
            session_date=session_date,
            topic=topic,
        )
    except (ValidationError, DuplicateRecordError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Attendance session created successfully: ID {session.session_id}")

    output_func("")


def view_attendance_session(
    attendance_service: AttendanceService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_session_selection_context(attendance_service, course_service, output_func)
    session_id = _prompt_required("Enter session ID: ", input_func, output_func)
    if session_id is None:
        output_func("View attendance session cancelled.")
        output_func("")
        return

    try:
        session = attendance_service.get_session(session_id)
        course = course_service.get_course_by_id(session.course_id)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_session_detail(session, course):
            output_func(line)

    output_func("")


def list_attendance_sessions(
    attendance_service: AttendanceService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_optional("Course code filter (optional): ", input_func)
    if course_code == "q":
        output_func("List attendance sessions cancelled.")
        output_func("")
        return

    date_from = _prompt_optional("Date from [YYYY-MM-DD] (optional): ", input_func)
    if date_from == "q":
        output_func("List attendance sessions cancelled.")
        output_func("")
        return

    date_to = _prompt_optional("Date to [YYYY-MM-DD] (optional): ", input_func)
    if date_to == "q":
        output_func("List attendance sessions cancelled.")
        output_func("")
        return

    topic_search = _prompt_optional("Topic search (optional): ", input_func)
    if topic_search == "q":
        output_func("List attendance sessions cancelled.")
        output_func("")
        return

    try:
        sessions = attendance_service.list_sessions(
            course_code=course_code,
            date_from=date_from,
            date_to=date_to,
            topic_search=topic_search,
        )
        course_labels = _course_labels_for_sessions(course_service, sessions)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_session_table(sessions, course_labels):
            output_func(line)

    output_func("")


def record_class_attendance(
    service: AttendanceService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_session_selection_context(service, course_service, output_func)
    session_id = _prompt_required("Enter session ID: ", input_func, output_func)
    if session_id is None:
        output_func("Record class attendance cancelled.")
        output_func("")
        return

    try:
        students = service.list_eligible_students(session_id)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
        output_func("")
        return

    if not students:
        output_func("No eligible students found for this session.")
        output_func("")
        return

    output_func("Enter q at any prompt to cancel.")
    entries = []
    for student in students:
        status = _prompt_attendance_status(
            "Status for "
            f"{student.student_number} {student.full_name} "
            f"[{_format_allowed_statuses()}] (blank for unknown): ",
            input_func,
            output_func,
            default=ATTENDANCE_UNKNOWN_STATUS,
        )
        if status is None:
            output_func("Record class attendance cancelled.")
            output_func("")
            return

        notes = _prompt_optional(
            f"Notes for {student.student_number} (optional): ",
            input_func,
        )
        if notes == "q":
            output_func("Record class attendance cancelled.")
            output_func("")
            return

        entries.append(
            AttendanceRegisterEntry(
                student_number=student.student_number,
                status=status,
                notes=notes,
            )
        )
        break

    if not _confirm("Save this class register? [y/N]: ", input_func, output_func):
        output_func("Record class attendance cancelled.")
        output_func("")
        return

    try:
        records = service.record_class_attendance(session_id, entries)
    except (
        ValidationError,
        DuplicateRecordError,
        RecordNotFoundError,
        DatabaseError,
    ) as error:
        output_func(str(error))
    else:
        output_func(f"Class attendance recorded successfully: {len(records)} records")

    output_func("")


def record_individual_attendance(
    service: AttendanceService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    for line in format_title("Record Individual Attendance"):
        output_func(line)
    output_func("Enter q at any prompt to cancel.")
    _show_session_selection_context(service, course_service, output_func)

    session_id = _prompt_required("Enter session ID: ", input_func, output_func)
    if session_id is None:
        output_func("Record attendance cancelled.")
        output_func("")
        return

    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Record attendance cancelled.")
        output_func("")
        return

    status = _prompt_attendance_status(
        f"Enter attendance status [{_format_allowed_statuses()}]: ",
        input_func,
        output_func,
    )
    if status is None:
        output_func("Record attendance cancelled.")
        output_func("")
        return

    notes = _prompt_optional("Enter notes (optional): ", input_func)
    if notes == "q":
        output_func("Record attendance cancelled.")
        output_func("")
        return

    try:
        record = service.record_attendance(
            session_id=session_id,
            student_number=student_number,
            status=status,
            notes=notes,
        )
    except (
        ValidationError,
        DuplicateRecordError,
        RecordNotFoundError,
        DatabaseError,
    ) as error:
        output_func(str(error))
    else:
        output_func(f"Attendance recorded successfully: ID {record.attendance_record_id}")

    output_func("")


def update_attendance_record(
    service: AttendanceService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_session_selection_context(service, course_service, output_func)
    session_id = _prompt_required("Enter session ID: ", input_func, output_func)
    if session_id is None:
        output_func("Update attendance record cancelled.")
        output_func("")
        return

    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Update attendance record cancelled.")
        output_func("")
        return

    try:
        current_record = service.get_attendance_record(session_id, student_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
        output_func("")
        return

    output_func(f"Current status: {format_status(current_record.status)}")
    output_func(f"Current notes : {current_record.notes or '-'}")
    output_func("Leave blank to keep the current value. Enter - to clear notes.")

    status = _prompt_attendance_status(
        f"Enter attendance status [{_format_allowed_statuses()}]: ",
        input_func,
        output_func,
        default=current_record.status,
    )
    if status is None:
        output_func("Update attendance record cancelled.")
        output_func("")
        return

    notes = _prompt_update_optional_value("Enter notes", current_record.notes, input_func)
    if notes == "q":
        output_func("Update attendance record cancelled.")
        output_func("")
        return

    try:
        updated = service.update_attendance(
            session_id=session_id,
            student_number=student_number,
            status=status,
            notes=notes,
        )
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(
            f"Attendance record updated successfully: ID {updated.attendance_record_id}"
        )

    output_func("")


def view_session_register(
    attendance_service: AttendanceService,
    student_service: StudentService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_session_selection_context(attendance_service, course_service, output_func)
    session_id = _prompt_required("Enter session ID: ", input_func, output_func)
    if session_id is None:
        output_func("View session register cancelled.")
        output_func("")
        return

    try:
        records = attendance_service.list_session_attendance(session_id)
        student_labels = _student_labels_for_records(student_service, records)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_session_register_table(records, student_labels):
            output_func(line)

    output_func("")


def view_student_attendance(
    attendance_service: AttendanceService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("View student attendance cancelled.")
        output_func("")
        return

    course_code = _prompt_optional("Course code filter (optional): ", input_func)
    if course_code == "q":
        output_func("View student attendance cancelled.")
        output_func("")
        return

    try:
        records = attendance_service.list_student_attendance(
            student_number=student_number,
            course_code=course_code,
        )
        session_context = _session_context_for_records(
            attendance_service,
            course_service,
            records,
        )
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_student_attendance_table(records, session_context):
            output_func(line)

    output_func("")


def attendance_summary(
    attendance_service: AttendanceService,
    course_service: CourseService,
    student_service: StudentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    summary_type = _prompt_summary_type(input_func, output_func)
    if summary_type is None:
        output_func("Attendance summary cancelled.")
        output_func("")
        return

    if summary_type == "student":
        _show_student_summary(
            attendance_service,
            course_service,
            student_service,
            input_func,
            output_func,
        )
        return

    _show_low_attendance_summary(
        attendance_service,
        student_service,
        input_func,
        output_func,
    )


def format_session_detail(session: AttendanceSession, course: Course) -> list[str]:
    """Return a compact one-session display."""
    lines = format_title("Attendance Session Details")
    lines.extend(
        [
            f"{'Session ID':<16}: {session.session_id}",
            f"{'Date':<16}: {session.session_date}",
            f"{'Course':<16}: {_course_label(course)}",
            f"{'Topic':<16}: {_format_topic(session.topic)}",
            f"{'Created':<16}: {session.created_at}",
        ]
    )
    return lines


def format_session_table(
    sessions: list[AttendanceSession],
    course_labels: dict[int, str] | None = None,
) -> list[str]:
    """Return an aligned attendance-session table."""
    if not sessions:
        return ["No attendance sessions found."]

    courses = course_labels or {}
    lines = [
        f"{'ID':<4} {'Date':<10} {'Course':<12} {'Topic'}",
        "-" * 70,
    ]
    for session in sessions:
        lines.append(
            f"{session.session_id:<4} "
            f"{session.session_date:<10} "
            f"{courses.get(session.course_id, f'Course {session.course_id}'):<12} "
            f"{_format_topic(session.topic)}"
        )

    return lines


def format_session_register_table(
    records: list[AttendanceRecord],
    student_labels: dict[int, str] | None = None,
) -> list[str]:
    """Return an aligned session-register table."""
    if not records:
        return ["No attendance records found for this session."]

    students = student_labels or {}
    lines = [
        f"{'Record':<7} {'Student':<26} {'Status':<9} {'Notes'}",
        "-" * 80,
    ]
    for record in records:
        lines.append(
            f"{record.attendance_record_id:<7} "
            f"{students.get(record.student_id, f'Student {record.student_id}'):<26} "
            f"{format_status(record.status):<9} "
            f"{record.notes or '-'}"
        )

    return lines


def format_student_attendance_table(
    records: list[AttendanceRecord],
    session_context: dict[int, tuple[AttendanceSession, str]] | None = None,
) -> list[str]:
    """Return an aligned student attendance history table."""
    if not records:
        return ["No attendance records found for this student."]

    context = session_context or {}
    lines = [
        f"{'Date':<10} {'Course':<12} {'Topic':<20} {'Status':<9} {'Notes'}",
        "-" * 86,
    ]
    for record in records:
        session, course_label = context.get(
            record.session_id,
            (
                AttendanceSession(record.session_id, 0, "-", "", "-"),
                "Course ?",
            ),
        )
        lines.append(
            f"{session.session_date:<10} "
            f"{course_label:<12} "
            f"{_format_topic(session.topic):<20} "
            f"{format_status(record.status):<9} "
            f"{record.notes or '-'}"
        )

    return lines


def format_attendance_summary(
    summary: AttendanceSummary,
    student_label: str,
    course_label: str,
) -> list[str]:
    """Return a compact attendance summary display."""
    lines = format_title("Attendance Summary")
    lines.extend(
        [
            f"{'Student':<22}: {student_label}",
            f"{'Course':<22}: {course_label}",
            f"{'Total records':<22}: {summary.total_records}",
            f"{'Present':<22}: {summary.present_count}",
            f"{'Late':<22}: {summary.late_count}",
            f"{'Absent':<22}: {summary.absent_count}",
            f"{'Excused':<22}: {summary.excused_count}",
            f"{'Unknown':<22}: {summary.unknown_count}",
            f"{'Attendance percentage':<22}: {_format_percentage(summary)}",
        ]
    )
    return lines


def format_low_attendance_table(
    summaries: list[AttendanceSummary],
    student_labels: dict[int, str] | None = None,
) -> list[str]:
    """Return students below a supplied attendance threshold."""
    if not summaries:
        return ["No low-attendance students found."]

    students = student_labels or {}
    lines = [
        f"{'Student':<28} {'Records':<8} {'Attended':<8} {'Absent':<7} {'Percentage'}",
        "-" * 74,
    ]
    for summary in summaries:
        lines.append(
            f"{students.get(summary.student_id, f'Student {summary.student_id}'):<28} "
            f"{summary.total_records:<8} "
            f"{summary.attended_count:<8} "
            f"{summary.absent_count:<7} "
            f"{_format_percentage(summary)}"
        )

    return lines


def _show_student_summary(
    attendance_service: AttendanceService,
    course_service: CourseService,
    student_service: StudentService,
    input_func,
    output_func,
) -> None:
    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Attendance summary cancelled.")
        output_func("")
        return

    course_code = _prompt_optional("Course code filter (optional): ", input_func)
    if course_code == "q":
        output_func("Attendance summary cancelled.")
        output_func("")
        return

    try:
        summary = attendance_service.calculate_student_attendance(
            student_number=student_number,
            course_code=course_code,
        )
        student = student_service.get_student_by_id(summary.student_id)
        course_label = "All courses"
        if summary.course_id is not None:
            course_label = course_service.get_course_by_id(summary.course_id).course_code
        summary = summary.total_records
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_attendance_summary(
            summary,
            _student_label(student),
            course_label,
        ):
            output_func(line)

    output_func("")


def _show_low_attendance_summary(
    attendance_service: AttendanceService,
    student_service: StudentService,
    input_func,
    output_func,
) -> None:
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Attendance summary cancelled.")
        output_func("")
        return

    threshold = _prompt_optional(
        f"Threshold percentage [{DEFAULT_LOW_ATTENDANCE_THRESHOLD}]: ",
        input_func,
    )
    if threshold == "q":
        output_func("Attendance summary cancelled.")
        output_func("")
        return
    threshold = threshold or DEFAULT_LOW_ATTENDANCE_THRESHOLD

    try:
        summaries = attendance_service.list_low_attendance_students(
            course_code=course_code,
            threshold_percentage=threshold,
        )
        student_labels = _student_labels_for_summaries(student_service, summaries)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_low_attendance_table(summaries, student_labels):
            output_func(line)

    output_func("")


def _course_labels_for_sessions(
    course_service: CourseService,
    sessions: list[AttendanceSession],
) -> dict[int, str]:
    labels = {}
    for session in sessions:
        if session.session_id in labels:
            continue
        try:
            labels[session.session_id] = course_service.get_course_by_id(
                session.course_id
            ).course_code
        except (RecordNotFoundError, DatabaseError):
            labels[session.session_id] = f"Course {session.course_id}"

    return labels


def _student_labels_for_records(
    student_service: StudentService,
    records: list[AttendanceRecord],
) -> dict[int, str]:
    labels = {}
    for record in records:
        if record.student_id in labels:
            continue
        try:
            labels[record.student_id] = _student_label(
                student_service.get_student_by_id(record.student_id)
            )
        except (RecordNotFoundError, DatabaseError):
            labels[record.student_id] = f"Student {record.student_id}"

    return labels


def _student_labels_for_summaries(
    student_service: StudentService,
    summaries: list[AttendanceSummary],
) -> dict[int, str]:
    labels = {}
    for summary in summaries:
        if summary.student_id in labels:
            continue
        try:
            labels[summary.student_id] = _student_label(
                student_service.get_student_by_id(summary.student_id)
            )
        except (RecordNotFoundError, DatabaseError):
            labels[summary.student_id] = f"Student {summary.student_id}"

    return labels


def _session_context_for_records(
    attendance_service: AttendanceService,
    course_service: CourseService,
    records: list[AttendanceRecord],
) -> dict[int, tuple[AttendanceSession, str]]:
    context = {}
    for record in records:
        if record.session_id in context:
            continue
        try:
            session = attendance_service.get_session(record.session_id)
            course_label = course_service.get_course_by_id(session.course_id).course_code
        except (ValidationError, RecordNotFoundError, DatabaseError):
            session = AttendanceSession(record.session_id, 0, "-", "", "-")
            course_label = "Course ?"
        context[record.session_id] = (session, course_label)

    return context


def _student_label(student: Student) -> str:
    return f"{student.student_number} {student.full_name}"


def _course_label(course: Course) -> str:
    return f"{course.course_code} - {course.course_name}"


def _format_topic(topic: str) -> str:
    return topic or "-"


def _format_allowed_statuses() -> str:
    return "/".join(ATTENDANCE_STATUSES)


def _format_percentage(summary: AttendanceSummary) -> str:
    if summary.attendance_percentage is None:
        if summary.total_records == 0:
            return "No attendance recorded"
        return "No percentage available"

    return f"{summary.attendance_percentage:.2f}%"


def _show_session_selection_context(
    attendance_service: AttendanceService,
    course_service: CourseService,
    output_func,
) -> None:
    try:
        sessions = attendance_service.list_sessions()
        course_labels = _course_labels_for_sessions(course_service, sessions)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
        return

    output_func("Attendance sessions:")
    for line in format_session_table(sessions, course_labels):
        output_func(line)


def _prompt_required(prompt: str, input_func, output_func) -> str | None:
    return prompt_required(prompt, input_func, output_func)


def _prompt_optional(prompt: str, input_func) -> str | None:
    return prompt_optional(prompt, input_func)


def _prompt_update_optional_value(
    prompt: str,
    current_value: str | None,
    input_func,
) -> str | None:
    display_value = current_value or "-"
    value = _read_text(f"{prompt} [{display_value}]: ", input_func)
    if _is_cancel(value):
        return "q"
    if value.strip() == "-":
        return None

    return value.strip() or current_value


def _prompt_attendance_status(
    prompt: str,
    input_func,
    output_func,
    default: str | None = None,
) -> str | None:
    while True:
        value = _read_text(prompt, input_func).strip().lower()
        if _is_cancel(value):
            return None
        if not value and default is not None:
            return default
        if value in ATTENDANCE_STATUSES:
            return value
        output_func(f"Choose one of: {', '.join(ATTENDANCE_STATUSES)}.")


def _prompt_summary_type(input_func, output_func) -> str | None:
    prompt = "Summary type [student/low] (blank for student): "
    while True:
        value = _read_text(prompt, input_func).strip().lower()
        if _is_cancel(value):
            return None
        if not value:
            return "student"
        if value in ("student", "low"):
            return value
        output_func("Choose student or low.")


def _prompt_yes_no(prompt: str, input_func, output_func, default: bool) -> bool | None:
    return prompt_yes_no(prompt, input_func, output_func, default)


def _confirm(prompt: str, input_func, output_func) -> bool:
    return confirm(prompt, input_func, output_func)


def _read_text(prompt: str, input_func) -> str:
    return read_text(prompt, input_func)


def _is_cancel(value: str) -> bool:
    return is_cancel(value)
