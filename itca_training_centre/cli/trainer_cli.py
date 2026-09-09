"""Trainer Management and Trainer Assignment command-line screens."""

from dataclasses import dataclass

from ..config.settings import AppConfig
from ..models.course import Course
from ..models.trainer import Trainer
from ..models.trainer_assignment import ASSIGNMENT_STATUSES, TrainerAssignment
from ..services.course_service import CourseService
from ..services.trainer_assignment_service import TrainerAssignmentService
from ..services.trainer_service import TrainerService
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
class TrainerMenuOption:
    """A numbered Trainer Management menu option."""

    choice: str
    label: str


@dataclass(frozen=True)
class TrainerAssignmentMenuOption:
    """A numbered Trainer Assignments menu option."""

    choice: str
    label: str


TRAINER_MENU_OPTIONS = (
    TrainerMenuOption("1", "Register Trainer"),
    TrainerMenuOption("2", "View Trainer"),
    TrainerMenuOption("3", "List Trainers"),
    TrainerMenuOption("4", "Search Trainers"),
    TrainerMenuOption("5", "Update Trainer"),
    TrainerMenuOption("6", "Deactivate Trainer"),
    TrainerMenuOption("7", "Reactivate Trainer"),
    TrainerMenuOption("8", "Trainer Assignments"),
    TrainerMenuOption("0", "Back"),
)

ASSIGNMENT_MENU_OPTIONS = (
    TrainerAssignmentMenuOption("1", "Assign Trainer to Course"),
    TrainerAssignmentMenuOption("2", "View Trainer Assignments"),
    TrainerAssignmentMenuOption("3", "View Course Assignments"),
    TrainerAssignmentMenuOption("4", "Search / List Assignments"),
    TrainerAssignmentMenuOption("5", "Deactivate Assignment"),
    TrainerAssignmentMenuOption("6", "Reactivate Assignment"),
    TrainerAssignmentMenuOption("0", "Back"),
)

VALID_TRAINER_MENU_CHOICES = tuple(option.choice for option in TRAINER_MENU_OPTIONS)
VALID_ASSIGNMENT_MENU_CHOICES = tuple(option.choice for option in ASSIGNMENT_MENU_OPTIONS)


def run_trainer_menu(
    config: AppConfig,
    input_func=input,
    output_func=print,
    trainer_service: TrainerService | None = None,
    assignment_service: TrainerAssignmentService | None = None,
    course_service: CourseService | None = None,
) -> None:
    """Run the Trainer Management submenu."""
    trainers = trainer_service or TrainerService(config.paths.database_path)
    assignments = assignment_service or TrainerAssignmentService(config.paths.database_path)
    courses = course_service or CourseService(config.paths.database_path)

    while True:
        show_trainer_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_TRAINER_MENU_CHOICES):
            output_func("Choose a number from the Trainer Management menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Main Menu.")
            output_func("")
            return

        if choice == "1":
            register_trainer(trainers, input_func=input_func, output_func=output_func)
        elif choice == "2":
            view_trainer(trainers, input_func=input_func, output_func=output_func)
        elif choice == "3":
            list_trainers(trainers, input_func=input_func, output_func=output_func)
        elif choice == "4":
            search_trainers(trainers, input_func=input_func, output_func=output_func)
        elif choice == "5":
            update_trainer(trainers, input_func=input_func, output_func=output_func)
        elif choice == "6":
            deactivate_trainer(trainers, input_func=input_func, output_func=output_func)
        elif choice == "7":
            reactivate_trainer(trainers, input_func=input_func, output_func=output_func)
        elif choice == "8":
            run_assignment_menu(
                trainers,
                assignments,
                courses,
                input_func=input_func,
                output_func=output_func,
            )


def show_trainer_menu(output_func=print) -> None:
    """Display the Trainer Management submenu."""
    for line in format_title("Trainer Management"):
        output_func(line)

    for option in TRAINER_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def run_assignment_menu(
    trainer_service: TrainerService,
    assignment_service: TrainerAssignmentService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    """Run the Trainer Assignments submenu."""
    while True:
        show_assignment_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_ASSIGNMENT_MENU_CHOICES):
            output_func("Choose a number from the Trainer Assignments menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Trainer Management.")
            output_func("")
            return

        if choice == "1":
            assign_trainer(assignment_service, input_func=input_func, output_func=output_func)
        elif choice == "2":
            view_trainer_assignments(
                trainer_service,
                assignment_service,
                course_service,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "3":
            view_course_assignments(
                trainer_service,
                assignment_service,
                course_service,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "4":
            search_assignments(
                trainer_service,
                assignment_service,
                course_service,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "5":
            deactivate_assignment(
                assignment_service,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "6":
            reactivate_assignment(
                assignment_service,
                input_func=input_func,
                output_func=output_func,
            )


def show_assignment_menu(output_func=print) -> None:
    """Display the Trainer Assignments submenu."""
    for line in format_title("Trainer Assignments"):
        output_func(line)

    for option in ASSIGNMENT_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def register_trainer(
    service: TrainerService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    for line in format_title("Register Trainer"):
        output_func(line)
    output_func("Enter q at any prompt to cancel.")

    trainer_number = _prompt_required("Enter trainer number: ", input_func, output_func)
    if trainer_number is None:
        output_func("Trainer registration cancelled.")
        output_func("")
        return

    first_name = _prompt_required("Enter first name: ", input_func, output_func)
    if first_name is None:
        output_func("Trainer registration cancelled.")
        output_func("")
        return

    last_name = _prompt_required("Enter last name: ", input_func, output_func)
    if last_name is None:
        output_func("Trainer registration cancelled.")
        output_func("")
        return

    email = _prompt_optional("Enter email (optional): ", input_func)
    if email == "q":
        output_func("Trainer registration cancelled.")
        output_func("")
        return

    phone = _prompt_optional("Enter phone (optional): ", input_func)
    if phone == "q":
        output_func("Trainer registration cancelled.")
        output_func("")
        return

    try:
        trainer = service.register_trainer(
            trainer_number=trainer_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
        )
    except (ValidationError, DuplicateRecordError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Trainer registered successfully: {trainer.trainer_number}")

    output_func("")


def view_trainer(
    service: TrainerService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    trainer_number = _prompt_required("Enter trainer number: ", input_func, output_func)
    if trainer_number is None:
        output_func("View trainer cancelled.")
        output_func("")
        return

    try:
        trainer = service.get_trainer_by_number(trainer_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_trainer_detail(trainer):
            output_func(line)

    output_func("")


def list_trainers(
    service: TrainerService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    include_inactive = _prompt_yes_no(
        "Include inactive trainers? [y/N]: ",
        input_func,
        output_func,
        default=False,
    )
    if include_inactive is None:
        output_func("List trainers cancelled.")
        output_func("")
        return

    try:
        trainers = service.list_trainers(include_inactive=include_inactive)
    except DatabaseError as error:
        output_func(str(error))
    else:
        for line in format_trainer_table(trainers):
            output_func(line)

    output_func("")


def search_trainers(
    service: TrainerService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    search_text = _prompt_required("Enter search text: ", input_func, output_func)
    if search_text is None:
        output_func("Search trainers cancelled.")
        output_func("")
        return

    include_inactive = _prompt_yes_no(
        "Include inactive trainers? [y/N]: ",
        input_func,
        output_func,
        default=False,
    )
    if include_inactive is None:
        output_func("Search trainers cancelled.")
        output_func("")
        return

    try:
        trainers = service.search_trainers(
            search_text,
            include_inactive=include_inactive,
        )
    except (ValidationError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_trainer_table(trainers):
            output_func(line)

    output_func("")


def update_trainer(
    service: TrainerService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    trainer_number = _prompt_required("Enter trainer number: ", input_func, output_func)
    if trainer_number is None:
        output_func("Update trainer cancelled.")
        output_func("")
        return

    try:
        current_trainer = service.get_trainer_by_number(trainer_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
        output_func("")
        return

    for line in format_trainer_detail(current_trainer):
        output_func(line)

    output_func("Trainer number cannot be changed.")
    output_func("Leave blank to keep the current value.")
    output_func("Enter - to clear optional email or phone values.")

    first_name = _prompt_update_value(
        "Enter first name",
        current_trainer.first_name,
        input_func,
    )
    if first_name == "q":
        output_func("Update trainer cancelled.")
        output_func("")
        return

    last_name = _prompt_update_value(
        "Enter last name",
        current_trainer.last_name,
        input_func,
    )
    if last_name == "q":
        output_func("Update trainer cancelled.")
        output_func("")
        return

    email = _prompt_update_optional_value(
        "Enter email",
        current_trainer.email,
        input_func,
    )
    if email == "q":
        output_func("Update trainer cancelled.")
        output_func("")
        return

    phone = _prompt_update_optional_value(
        "Enter phone",
        current_trainer.phone,
        input_func,
    )
    if phone == "q":
        output_func("Update trainer cancelled.")
        output_func("")
        return

    try:
        updated_trainer = service.update_trainer(
            trainer_number=current_trainer.trainer_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
        )
    except (ValidationError, DuplicateRecordError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Trainer updated successfully: {updated_trainer.trainer_number}")

    output_func("")


def deactivate_trainer(
    service: TrainerService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    trainer_number = _prompt_required("Enter trainer number: ", input_func, output_func)
    if trainer_number is None:
        output_func("Deactivate trainer cancelled.")
        output_func("")
        return

    if not _confirm("Deactivate this trainer? [y/N]: ", input_func, output_func):
        output_func("Deactivate trainer cancelled.")
        output_func("")
        return

    try:
        trainer = service.deactivate_trainer(trainer_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Trainer is now inactive: {trainer.trainer_number}")

    output_func("")


def reactivate_trainer(
    service: TrainerService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    trainer_number = _prompt_required("Enter trainer number: ", input_func, output_func)
    if trainer_number is None:
        output_func("Reactivate trainer cancelled.")
        output_func("")
        return

    if not _confirm("Reactivate this trainer? [y/N]: ", input_func, output_func):
        output_func("Reactivate trainer cancelled.")
        output_func("")
        return

    try:
        trainer = service.reactivate_trainer(trainer_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Trainer is now active: {trainer.trainer_number}")

    output_func("")


def assign_trainer(
    service: TrainerAssignmentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    for line in format_title("Assign Trainer to Course"):
        output_func(line)
    output_func("Enter q at any prompt to cancel.")

    trainer_number = _prompt_required("Enter trainer number: ", input_func, output_func)
    if trainer_number is None:
        output_func("Trainer assignment cancelled.")
        output_func("")
        return

    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Trainer assignment cancelled.")
        output_func("")
        return

    assigned_from = _prompt_required(
        "Enter assigned-from date [YYYY-MM-DD]: ",
        input_func,
        output_func,
    )
    if assigned_from is None:
        output_func("Trainer assignment cancelled.")
        output_func("")
        return

    try:
        assignment = service.assign_trainer(
            trainer_number=trainer_number,
            course_code=course_code,
            assigned_from=assigned_from,
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
            "Trainer assigned successfully: "
            f"{trainer_number.strip().upper()} -> {course_code.strip().upper()} "
            f"(ID {assignment.assignment_id})"
        )

    output_func("")


def view_trainer_assignments(
    trainer_service: TrainerService,
    assignment_service: TrainerAssignmentService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    trainer_number = _prompt_required("Enter trainer number: ", input_func, output_func)
    if trainer_number is None:
        output_func("View trainer assignments cancelled.")
        output_func("")
        return

    filter_choice = _prompt_assignment_status_filter(input_func, output_func)
    if filter_choice is None:
        output_func("View trainer assignments cancelled.")
        output_func("")
        return

    include_ended, status = filter_choice
    try:
        assignments = assignment_service.list_trainer_assignments(
            trainer_number=trainer_number,
            include_ended=include_ended,
            status=status,
        )
        labels = _labels_for_assignments(trainer_service, course_service, assignments)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_assignment_table(
            assignments,
            labels[0],
            labels[1],
            empty_message="No assignments found for this trainer.",
        ):
            output_func(line)

    output_func("")


def view_course_assignments(
    trainer_service: TrainerService,
    assignment_service: TrainerAssignmentService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("View course assignments cancelled.")
        output_func("")
        return

    filter_choice = _prompt_assignment_status_filter(input_func, output_func)
    if filter_choice is None:
        output_func("View course assignments cancelled.")
        output_func("")
        return

    include_ended, status = filter_choice
    try:
        assignments = assignment_service.list_course_assignments(
            course_code=course_code,
            include_ended=include_ended,
            status=status,
        )
        labels = _labels_for_assignments(trainer_service, course_service, assignments)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_assignment_table(
            assignments,
            labels[0],
            labels[1],
            empty_message="No assignments found for this course.",
        ):
            output_func(line)

    output_func("")


def search_assignments(
    trainer_service: TrainerService,
    assignment_service: TrainerAssignmentService,
    course_service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    trainer_number = _prompt_optional("Trainer number filter (optional): ", input_func)
    if trainer_number == "q":
        output_func("Search assignments cancelled.")
        output_func("")
        return

    course_code = _prompt_optional("Course code filter (optional): ", input_func)
    if course_code == "q":
        output_func("Search assignments cancelled.")
        output_func("")
        return

    filter_choice = _prompt_assignment_status_filter(input_func, output_func)
    if filter_choice is None:
        output_func("Search assignments cancelled.")
        output_func("")
        return

    include_ended, status = filter_choice
    try:
        assignments = assignment_service.list_filtered_assignments(
            trainer_number=trainer_number,
            course_code=course_code,
            include_ended=include_ended,
            status=status,
        )
        labels = _labels_for_assignments(trainer_service, course_service, assignments)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_assignment_table(assignments, labels[0], labels[1]):
            output_func(line)

    output_func("")


def deactivate_assignment(
    service: TrainerAssignmentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    trainer_number = _prompt_required("Enter trainer number: ", input_func, output_func)
    if trainer_number is None:
        output_func("Deactivate assignment cancelled.")
        output_func("")
        return

    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Deactivate assignment cancelled.")
        output_func("")
        return

    assigned_to = _prompt_optional("Enter assigned-to date [YYYY-MM-DD] (optional): ", input_func)
    if assigned_to == "q":
        output_func("Deactivate assignment cancelled.")
        output_func("")
        return

    if not _confirm("Deactivate this assignment? [y/N]: ", input_func, output_func):
        output_func("Deactivate assignment cancelled.")
        output_func("")
        return

    try:
        assignment = service.end_assignment(
            trainer_number=trainer_number,
            course_code=course_code,
            assigned_to=assigned_to,
        )
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Trainer assignment is now ended: ID {assignment.assignment_id}")

    output_func("")


def reactivate_assignment(
    service: TrainerAssignmentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    trainer_number = _prompt_required("Enter trainer number: ", input_func, output_func)
    if trainer_number is None:
        output_func("Reactivate assignment cancelled.")
        output_func("")
        return

    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Reactivate assignment cancelled.")
        output_func("")
        return

    if not _confirm("Reactivate this assignment? [y/N]: ", input_func, output_func):
        output_func("Reactivate assignment cancelled.")
        output_func("")
        return

    try:
        assignment = service.reactivate_assignment(
            trainer_number=trainer_number,
            course_code=course_code,
        )
    except (
        ValidationError,
        DuplicateRecordError,
        RecordNotFoundError,
        DatabaseError,
    ) as error:
        output_func(str(error))
    else:
        output_func(f"Trainer assignment is now active: ID {assignment.assignment_id}")

    output_func("")


def format_trainer_detail(trainer: Trainer) -> list[str]:
    """Return a compact one-trainer display."""
    lines = format_title("Trainer Details")
    lines.extend(
        [
            f"{'ID':<16}: {trainer.trainer_id}",
            f"{'Trainer number':<16}: {trainer.trainer_number}",
            f"{'Name':<16}: {trainer.full_name}",
            f"{'Email':<16}: {trainer.email or '-'}",
            f"{'Phone':<16}: {trainer.phone or '-'}",
            f"{'Status':<16}: {format_status(trainer.status)}",
            f"{'Created':<16}: {trainer.created_at}",
            f"{'Updated':<16}: {trainer.updated_at}",
        ]
    )
    return lines


def format_trainer_table(trainers: list[Trainer]) -> list[str]:
    """Return an aligned trainer table or a useful empty-state line."""
    if not trainers:
        return ["No trainers found."]

    lines = [
        f"{'Trainer No.':<14} {'Name':<28} {'Status':<10} {'Email'}",
        "-" * 72,
    ]
    for trainer in trainers:
        lines.append(
            f"{trainer.trainer_number:<14} "
            f"{trainer.full_name:<28} "
            f"{format_status(trainer.status):<10} "
            f"{trainer.email or '-'}"
        )

    return lines


def format_assignment_table(
    assignments: list[TrainerAssignment],
    trainer_labels: dict[int, str] | None = None,
    course_labels: dict[int, str] | None = None,
    empty_message: str = "No assignments found.",
) -> list[str]:
    """Return an aligned trainer-assignment table."""
    if not assignments:
        return [empty_message]

    trainers = trainer_labels or {}
    courses = course_labels or {}
    lines = [
        f"{'ID':<4} {'Trainer':<24} {'Course':<10} {'From':<10} {'To':<10} {'Status'}",
        "-" * 76,
    ]
    for assignment in assignments:
        trainer_label = trainers.get(assignment.trainer_id, f"Trainer {assignment.trainer_id}")
        course_label = courses.get(assignment.course_id, f"Course {assignment.course_id}")
        lines.append(
            f"{assignment.assignment_id:<4} "
            f"{trainer_label:<24} "
            f"{course_label:<10} "
            f"{assignment.assigned_from:<10} "
            f"{assignment.assigned_to or '-':<10} "
            f"{format_status(assignment.status)}"
        )

    return lines


def _labels_for_assignments(
    trainer_service: TrainerService,
    course_service: CourseService,
    assignments: list[TrainerAssignment],
) -> tuple[dict[int, str], dict[int, str]]:
    trainer_labels = {}
    course_labels = {}

    for assignment in assignments:
        if assignment.trainer_id not in trainer_labels:
            try:
                trainer = trainer_service.get_trainer_by_id(assignment.trainer_id)
            except (RecordNotFoundError, DatabaseError):
                trainer_labels[assignment.trainer_id] = f"Trainer {assignment.trainer_id}"
            else:
                trainer_labels[assignment.trainer_id] = _trainer_label(trainer)

        if assignment.course_id not in course_labels:
            try:
                course = course_service.get_course_by_id(assignment.course_id)
            except (RecordNotFoundError, DatabaseError):
                course_labels[assignment.course_id] = f"Course {assignment.course_id}"
            else:
                course_labels[assignment.course_id] = course.course_code

    return trainer_labels, course_labels


def _trainer_label(trainer: Trainer) -> str:
    return f"{trainer.trainer_number} {trainer.full_name}"


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


def _prompt_assignment_status_filter(input_func, output_func) -> tuple[bool, str | None] | None:
    prompt = "Filter by status [active/ended/all] (blank for active): "
    while True:
        value = _read_text(prompt, input_func).strip().lower()
        if _is_cancel(value):
            return None
        if not value:
            return False, None
        if value == "all":
            return True, None
        if value in ASSIGNMENT_STATUSES:
            return value != "active", value
        output_func(f"Choose one of: {', '.join((*ASSIGNMENT_STATUSES, 'all'))}.")


def _prompt_yes_no(prompt: str, input_func, output_func, default: bool) -> bool | None:
    return prompt_yes_no(prompt, input_func, output_func, default)


def _confirm(prompt: str, input_func, output_func) -> bool:
    return confirm(prompt, input_func, output_func)


def _read_text(prompt: str, input_func) -> str:
    return read_text(prompt, input_func)


def _is_cancel(value: str) -> bool:
    return is_cancel(value)
