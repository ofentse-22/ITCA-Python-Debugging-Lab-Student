"""Course Enrolment command-line screens."""

from dataclasses import dataclass

from ..config.settings import AppConfig
from ..models.course import Course
from ..models.course_enrolment import ENROLMENT_STATUSES, CourseEnrolment
from ..models.student import Student
from ..services.course_enrolment_service import CourseEnrolmentService
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


@dataclass(frozen=True)
class EnrolmentMenuOption:
    """A numbered Course Enrolments menu option."""

    choice: str
    label: str


ENROLMENT_MENU_OPTIONS = (
    EnrolmentMenuOption("1", "Enrol Student in Course"),
    EnrolmentMenuOption("2", "View Student Enrolments"),
    EnrolmentMenuOption("3", "View Course Enrolments"),
    EnrolmentMenuOption("4", "Search / List Enrolments"),
    EnrolmentMenuOption("5", "Cancel Enrolment"),
    EnrolmentMenuOption("0", "Back"),
)

VALID_ENROLMENT_MENU_CHOICES = tuple(option.choice for option in ENROLMENT_MENU_OPTIONS)


def run_enrolment_menu(
    config: AppConfig,
    input_func=input,
    output_func=print,
    enrolment_service: CourseEnrolmentService | None = None,
    student_service: StudentService | None = None,
    course_service: CourseService | None = None,
) -> None:
    """Run the Course Enrolments submenu."""
    enrolments = enrolment_service or CourseEnrolmentService(config.paths.database_path)
    students = student_service or StudentService(config.paths.database_path)
    courses = course_service or CourseService(config.paths.database_path)

    while True:
        show_enrolment_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_ENROLMENT_MENU_CHOICES):
            output_func("Choose a number from the Course Enrolments menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Main Menu.")
            output_func("")
            return

        if choice == "1":
            enrol_student(enrolments, input_func=input_func, output_func=output_func)
        elif choice == "2":
            view_student_enrolments(
                enrolments,
                students,
                courses,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "3":
            view_course_enrolments(
                enrolments,
                students,
                courses,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "4":
            search_enrolments(
                enrolments,
                students,
                courses,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "5":
            cancel_enrolment(enrolments, input_func=input_func, output_func=output_func)


def show_enrolment_menu(output_func=print) -> None:
    """Display the Course Enrolments submenu."""
    for line in format_title("Course Enrolments"):
        output_func(line)

    for option in ENROLMENT_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def enrol_student(
    service: CourseEnrolmentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    for line in format_title("Enrol Student in Course"):
        output_func(line)
    output_func("Enter q at any prompt to cancel.")

    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Course enrolment cancelled.")
        output_func("")
        return

    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Course enrolment cancelled.")
        output_func("")
        return

    enrolment_date = _prompt_required(
        "Enter enrolment date [YYYY-MM-DD]: ",
        input_func,
        output_func,
    )
    if enrolment_date is None:
        output_func("Course enrolment cancelled.")
        output_func("")
        return

    try:
        enrolment = service.enrol_student(
            student_number=student_number,
            course_code=course_code,
            enrolment_date=enrolment_date,
        )
    except (
        ValidationError,
        DuplicateRecordError,
        RecordNotFoundError,
        DatabaseError,
    ) as error:
        output_func(str(error))
    else:
        output_func(
            "Student enrolled successfully: "
            f"{student_number.strip().upper()} -> {course_code.strip().upper()} "
            f"(ID {enrolment.enrolment_id})"
        )

    output_func("")


def view_student_enrolments(
    enrolment_service: CourseEnrolmentService,
    student_service: StudentService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("View student enrolments cancelled.")
        output_func("")
        return

    filter_choice = _prompt_enrolment_status_filter(input_func, output_func)
    if filter_choice is None:
        output_func("View student enrolments cancelled.")
        output_func("")
        return

    include_historical, status = filter_choice
    try:
        enrolments = enrolment_service.list_student_enrolments(
            student_number=student_number,
            include_historical=include_historical,
            status=status,
        )
        labels = _labels_for_enrolments(student_service, course_service, enrolments)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_enrolment_table(
            enrolments,
            labels[0],
            labels[1],
            empty_message="No enrolments found for this student.",
        ):
            output_func(line)

    output_func("")


def view_course_enrolments(
    enrolment_service: CourseEnrolmentService,
    student_service: StudentService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("View course enrolments cancelled.")
        output_func("")
        return

    filter_choice = _prompt_enrolment_status_filter(input_func, output_func)
    if filter_choice is None:
        output_func("View course enrolments cancelled.")
        output_func("")
        return

    include_historical, status = filter_choice
    try:
        enrolments = enrolment_service.list_course_enrolments(
            course_code=course_code,
            include_historical=include_historical,
            status=status,
        )
        labels = _labels_for_enrolments(student_service, course_service, enrolments)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_enrolment_table(
            enrolments,
            labels[0],
            labels[1],
            empty_message="No enrolments found for this course.",
        ):
            output_func(line)

    output_func("")


def search_enrolments(
    enrolment_service: CourseEnrolmentService,
    student_service: StudentService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    student_number = _prompt_optional("Student number filter (optional): ", input_func)
    if student_number == "q":
        output_func("Search enrolments cancelled.")
        output_func("")
        return

    course_code = _prompt_optional("Course code filter (optional): ", input_func)
    if course_code == "q":
        output_func("Search enrolments cancelled.")
        output_func("")
        return

    filter_choice = _prompt_enrolment_status_filter(input_func, output_func)
    if filter_choice is None:
        output_func("Search enrolments cancelled.")
        output_func("")
        return

    include_historical, status = filter_choice
    try:
        enrolments = enrolment_service.list_filtered_enrolments(
            student_number=student_number,
            course_code=course_code,
            include_historical=include_historical,
            status=status,
        )
        labels = _labels_for_enrolments(student_service, course_service, enrolments)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_enrolment_table(enrolments, labels[0], labels[1]):
            output_func(line)

    output_func("")


def cancel_enrolment(
    service: CourseEnrolmentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Cancel enrolment cancelled.")
        output_func("")
        return

    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Cancel enrolment cancelled.")
        output_func("")
        return

    cancelled_at = _prompt_required(
        "Enter cancellation date [YYYY-MM-DD]: ",
        input_func,
        output_func,
    )
    if cancelled_at is None:
        output_func("Cancel enrolment cancelled.")
        output_func("")
        return

    reason = _prompt_required("Enter cancellation reason: ", input_func, output_func)
    if reason is None:
        output_func("Cancel enrolment cancelled.")
        output_func("")
        return

    if not _confirm("Cancel this enrolment? [y/N]: ", input_func, output_func):
        output_func("Cancel enrolment cancelled.")
        output_func("")
        return

    try:
        enrolment = service.cancel_enrolment(
            student_number=student_number,
            course_code=course_code,
            cancelled_at=cancelled_at,
            cancellation_reason=reason,
        )
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Course enrolment cancelled: ID {enrolment.enrolment_id}")

    output_func("")


def format_enrolment_table(
    enrolments: list[CourseEnrolment],
    student_labels: dict[int, str] | None = None,
    course_labels: dict[int, str] | None = None,
    empty_message: str = "No enrolments found.",
) -> list[str]:
    """Return an aligned enrolment table or a useful empty-state line."""
    if not enrolments:
        return [empty_message]

    students = student_labels or {}
    courses = course_labels or {}
    lines = [
        f"{'ID':<4} {'Student':<24} {'Course':<10} {'Date':<10} {'Status':<9} {'Cancelled'}",
        "-" * 76,
    ]
    for enrolment in enrolments:
        student_label = students.get(enrolment.student_id, f"Student {enrolment.student_id}")
        course_label = courses.get(enrolment.course_id, f"Course {enrolment.course_id}")
        lines.append(
            f"{enrolment.enrolment_id:<4} "
            f"{student_label:<24} "
            f"{course_label:<10} "
            f"{enrolment.enrolment_date:<10} "
            f"{format_status(enrolment.status):<9} "
            f"{enrolment.cancelled_at or '-'}"
        )

    return lines


def _labels_for_enrolments(
    student_service: StudentService,
    course_service: CourseService,
    enrolments: list[CourseEnrolment],
) -> tuple[dict[int, str], dict[int, str]]:
    student_labels = {}
    course_labels = {}

    for enrolment in enrolments:
        if enrolment.student_id not in student_labels:
            try:
                student = student_service.get_student_by_id(enrolment.student_id)
            except (RecordNotFoundError, DatabaseError):
                student_labels[enrolment.student_id] = f"Student {enrolment.student_id}"
            else:
                student_labels[enrolment.student_id] = _student_label(student)

        if enrolment.course_id not in course_labels:
            try:
                course = course_service.get_course_by_id(enrolment.course_id)
            except (RecordNotFoundError, DatabaseError):
                course_labels[enrolment.course_id] = f"Course {enrolment.course_id}"
            else:
                course_labels[enrolment.course_id] = course.course_code

    return student_labels, course_labels


def _student_label(student: Student) -> str:
    return f"{student.student_number} {student.full_name}"


def _prompt_required(prompt: str, input_func, output_func) -> str | None:
    return prompt_required(prompt, input_func, output_func)


def _prompt_optional(prompt: str, input_func) -> str | None:
    return prompt_optional(prompt, input_func)


def _prompt_enrolment_status_filter(input_func, output_func) -> tuple[bool, str | None] | None:
    prompt = "Filter by status [active/completed/cancelled/all] (blank for active): "
    while True:
        value = _read_text(prompt, input_func).strip().lower()
        if _is_cancel(value):
            return None
        if not value:
            return False, None
        if value == "all":
            return True, None
        if value in ENROLMENT_STATUSES:
            return value != "active", value
        output_func(f"Choose one of: {', '.join((*ENROLMENT_STATUSES, 'all'))}.")


def _prompt_yes_no(prompt: str, input_func, output_func, default: bool) -> bool | None:
    return prompt_yes_no(prompt, input_func, output_func, default)


def _confirm(prompt: str, input_func, output_func) -> bool:
    return confirm(prompt, input_func, output_func)


def _read_text(prompt: str, input_func) -> str:
    return read_text(prompt, input_func)


def _is_cancel(value: str) -> bool:
    return is_cancel(value)
