"""Student Management command-line screens."""

from dataclasses import dataclass

from ..config.settings import AppConfig
from .models.student import Student
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
class StudentMenuOption:
    """A numbered Student Management menu option."""

    choice: str
    label: str


STUDENT_MENU_OPTIONS = (
    StudentMenuOption("1", "Register Student"),
    StudentMenuOption("2", "View Student"),
    StudentMenuOption("3", "List Students"),
    StudentMenuOption("4", "Search Students"),
    StudentMenuOption("5", "Update Student"),
    StudentMenuOption("6", "Deactivate Student"),
    StudentMenuOption("7", "Reactivate Student"),
    StudentMenuOption("0", "Back"),
)

VALID_STUDENT_MENU_CHOICES = tuple(option.choice for option in STUDENT_MENU_OPTIONS)


def run_student_menu(
    config: AppConfig,
    input_func=input,
    output_func=print,
    student_service: StudentService | None = None,
) -> None:
    """Run the Student Management submenu."""
    service = student_service or StudentService(config.paths.database_path)

    while True:
        show_student_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_STUDENT_MENU_CHOICES):
            output_func("Choose a number from the Student Management menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Main Menu.")
            output_func("")
            continue

        if choice == "1":
            register_student(service, input_func=input_func, output_func=output_func)
        elif choice == "2":
            view_student(service, input_func=input_func, output_func=output_func)
        elif choice == "3":
            list_students(service, input_func=input_func, output_func=output_func)
        elif choice == "4":
            search_students(service, input_func=input_func, output_func=output_func)
        elif choice == "5":
            update_student(service, input_func=input_func, output_func=output_func)
        elif choice == "6":
            deactivate_student(service, input_func=input_func, output_func=output_func)
        elif choice == "7":
            reactivate_student(service, input_func=input_func, output_func=output_func)


def show_student_menu(output_func=print) -> None:
    """Display the Student Management submenu."""
    for line in format_title("Student Management"):
        output_func(line)

    for option in STUDENT_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def register_student(
    service: StudentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    for line in format_title("Register Student"):
        output_func(line)
    output_func("Enter q at any prompt to cancel.")

    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Student registration cancelled.")
        output_func("")
        return

    first_name = _prompt_required("Enter first name: ", input_func, output_func)
    if first_name is None:
        output_func("Student registration cancelled.")
        output_func("")
        return

    last_name = _prompt_required("Enter last name: ", input_func, output_func)
    if last_name is None:
        output_func("Student registration cancelled.")
        output_func("")
        return

    email = _prompt_optional("Enter email (optional): ", input_func)
    if email == "q":
        output_func("Student registration cancelled.")
        output_func("")
        return

    phone = _prompt_optional("Enter phone (optional): ", input_func)
    if phone == "q":
        output_func("Student registration cancelled.")
        output_func("")
        return

    try:
        student = service.register_student(
            student_number=student_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
        )
    except (ValidationError, DuplicateRecordError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func("Student registered successfully: " + student.student_id)

    output_func("")


def view_student(
    service: StudentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("View student cancelled.")
        output_func("")
        return

    try:
        student = service.get_student_by_number(student_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_student_detail(student):
            output_func(line)

    output_func("")


def list_students(
    service: StudentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    include_inactive = _prompt_yes_no(
        "Include inactive students? [y/N]: ",
        input_func,
        output_func,
        default=False,
    )
    if include_inactive is None:
        output_func("List students cancelled.")
        output_func("")
        return

    try:
        students = service.list_students(include_inactive=include_inactive)
    except DatabaseError as error:
        output_func(str(error))
    else:
        for line in format_student_table(students):
            output_func(line)

    output_func("")


def search_students(
    service: StudentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    search_text = _prompt_required("Enter search text: ", input_func, output_func)
    if search_text is None:
        output_func("Search students cancelled.")
        output_func("")
        return

    include_inactive = _prompt_yes_no(
        "Include inactive students? [y/N]: ",
        input_func,
        output_func,
        default=False,
    )
    if include_inactive is None:
        output_func("Search students cancelled.")
        output_func("")
        return

    try:
        students = service.search_students(
            search_text,
            include_inactive=include_inactive,
        )
    except (ValidationError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_student_table(students):
            output_func(line)

    output_func("")


def update_student(
    service: StudentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Update student cancelled.")
        output_func("")
        return

    try:
        current_student = service.get_student_by_number(student_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
        output_func("")
        return

    for line in format_student_detail(current_student):
        output_func(line)

    output_func("Leave blank to keep the current value.")
    output_func("Enter - to clear optional email or phone values.")

    first_name = _prompt_update_value(
        "Enter first name",
        current_student.first_name,
        input_func,
    )
    if first_name == "q":
        output_func("Update student cancelled.")
        output_func("")
        return

    last_name = _prompt_update_value(
        "Enter last name",
        current_student.last_name,
        input_func,
    )
    if last_name == "q":
        output_func("Update student cancelled.")
        output_func("")
        return

    email = _prompt_update_optional_value(
        "Enter email",
        current_student.email,
        input_func,
    )
    if email == "q":
        output_func("Update student cancelled.")
        output_func("")
        return

    phone = _prompt_update_optional_value(
        "Enter phone",
        current_student.phone,
        input_func,
    )
    if phone == "q":
        output_func("Update student cancelled.")
        output_func("")
        return

    try:
        updated_student = service.update_student(
            student_number=current_student.student_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
        )
    except (ValidationError, DuplicateRecordError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Student updated successfully: {updated_student.student_number}")

    output_func("")


def deactivate_student(
    service: StudentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Deactivate student cancelled.")
        output_func("")
        return

    if not _confirm("Deactivate this student? [y/N]: ", input_func, output_func):
        output_func("Deactivate student cancelled.")
        output_func("")
        return

    try:
        student = service.deactivate_student(student_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Student is now inactive: {student.student_number}")

    output_func("")


def reactivate_student(
    service: StudentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Reactivate student cancelled.")
        output_func("")
        return

    if not _confirm("Reactivate this student? [y/N]: ", input_func, output_func):
        output_func("Reactivate student cancelled.")
        output_func("")
        return

    try:
        student = service.reactivate_student(student_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Student is now active: {student.student_number}")

    output_func("")


def format_student_detail(student: Student) -> list[str]:
    """Return a compact one-student display."""
    lines = format_title("Student Details")
    lines.extend(
        [
            f"{'ID':<16}: {student.student_id}",
            f"{'Student number':<16}: {student.student_number}",
            f"{'Name':<16}: {student.full_name}",
            f"{'Email':<16}: {student.email or '-'}",
            f"{'Phone':<16}: {student.phone or '-'}",
            f"{'Status':<16}: {format_status(student.status)}",
            f"{'Created':<16}: {student.created_at}",
            f"{'Updated':<16}: {student.updated_at}",
        ]
    )
    return lines


def format_student_table(students: list[Student]) -> list[str]:
    """Return an aligned student table or a useful empty-state line."""
    if not students:
        return ["No students found."]

    lines = [
        f"{'Student No.':<14} {'Name':<28} {'Status':<10} {'Email'}",
        "-" * 72,
    ]
    for student in students:
        lines.append(
            f"{student.student_number:<14} "
            f"{student.full_name:<28} "
            f"{format_status(student.status):<10} "
            f"{student.email or '-'}"
        )

    return lines


def _prompt_required(prompt: str, input_func, output_func) -> str | None:
    return prompt_required(prompt, input_func, output_func)


def _prompt_optional(prompt: str, input_func) -> str | None:
    return prompt_optional(prompt, input_func)


def _prompt_update_value(prompt: str, current_value: str, input_func) -> str:
    value = _read_text(f"{prompt} [{current_value}]: ", input_func)
    if _is_cancel(value):
        return "q"

    return value.strip() or current_value


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


def _prompt_yes_no(prompt: str, input_func, output_func, default: bool) -> bool | None:
    return prompt_yes_no(prompt, input_func, output_func, default)


def _confirm(prompt: str, input_func, output_func) -> bool:
    return confirm(prompt, input_func, output_func)


def _read_text(prompt: str, input_func) -> str:
    return read_text(prompt, input_func)


def _is_cancel(value: str) -> bool:
    return is_cancel(value)
