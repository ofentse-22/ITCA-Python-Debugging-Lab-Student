"""Course and Module Management command-line screens."""

from dataclasses import dataclass
from decimal import Decimal

from ..config.settings import AppConfig
from ..models.course import COURSE_PLANNED_STATUS, COURSE_STATUSES, Course
from ..models.module import MODULE_ACTIVE_STATUS, MODULE_STATUSES, Module
from ..services.course_service import CourseService
from ..services.module_service import ModuleService
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
class CourseMenuOption:
    """A numbered Course Management menu option."""

    choice: str
    label: str


@dataclass(frozen=True)
class ModuleMenuOption:
    """A numbered Module Management menu option."""

    choice: str
    label: str


COURSE_MENU_OPTIONS = (
    CourseMenuOption("1", "Register Course"),
    CourseMenuOption("2", "View Course"),
    CourseMenuOption("3", "List Courses"),
    CourseMenuOption("4", "Search Courses"),
    CourseMenuOption("5", "Update Course"),
    CourseMenuOption("6", "Deactivate Course"),
    CourseMenuOption("7", "Reactivate Course"),
    CourseMenuOption("8", "Module Management"),
    CourseMenuOption("0", "Back"),
)

MODULE_MENU_OPTIONS = (
    ModuleMenuOption("1", "Add Module to Course"),
    ModuleMenuOption("2", "View Module"),
    ModuleMenuOption("3", "List Modules for Course"),
    ModuleMenuOption("4", "Search Modules"),
    ModuleMenuOption("5", "Update Module"),
    ModuleMenuOption("6", "Deactivate Module"),
    ModuleMenuOption("7", "Reactivate Module"),
    ModuleMenuOption("0", "Back"),
)

VALID_COURSE_MENU_CHOICES = tuple(option.choice for option in COURSE_MENU_OPTIONS)
VALID_MODULE_MENU_CHOICES = tuple(option.choice for option in MODULE_MENU_OPTIONS)


def run_course_menu(
    config: AppConfig,
    input_func=input,
    output_func=print,
    course_service: CourseService | None = None,
    module_service: ModuleService | None = None,
) -> None:
    """Run the Course and Module Management submenu."""
    courses = course_service or CourseService(config.paths.database_path)
    modules = module_service or ModuleService(config.paths.database_path)

    while True:
        show_course_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_COURSE_MENU_CHOICES):
            output_func("Choose a number from the Course Management menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Main Menu.")
            output_func("")
            return

        if choice == "1":
            register_course(courses, input_func=input_func, output_func=output_func)
        elif choice == "2":
            view_course(
                courses,
                modules,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "3":
            list_courses(courses, input_func=input_func, output_func=output_func)
        elif choice == "4":
            search_courses(courses, input_func=input_func, output_func=output_func)
        elif choice == "5":
            update_course(courses, input_func=input_func, output_func=output_func)
        elif choice == "6":
            deactivate_course(courses, input_func=input_func, output_func=output_func)
        elif choice == "7":
            reactivate_course(courses, input_func=input_func, output_func=output_func)
        elif choice == "8":
            run_module_menu(
                courses,
                modules,
                input_func=input_func,
                output_func=output_func,
            )


def show_course_menu(output_func=print) -> None:
    """Display the Course and Module Management submenu."""
    for line in format_title("Course and Module Management"):
        output_func(line)

    for class in COURSE_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def run_module_menu(
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    """Run the Module Management submenu."""
    while True:
        show_module_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_MODULE_MENU_CHOICES):
            output_func("Choose a number from the Module Management menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Course Management.")
            output_func("")
            return

        if choice == "1":
            add_module_to_course(
                module_service,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "2":
            view_module(
                course_service,
                module_service,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "3":
            list_modules_for_course(
                course_service,
                module_service,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "4":
            search_modules(
                course_service,
                module_service,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "5":
            update_module(
                course_service,
                module_service,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "6":
            deactivate_module(
                module_service,
                input_func=input_func,
                output_func=output_func,
            )
        elif choice == "7":
            reactivate_module(
                module_service,
                input_func=input_func,
                output_func=output_func,
            )


def show_module_menu(output_func=print) -> None:
    """Display the Module Management submenu."""
    for line in format_title("Module Management"):
        output_func(line)

    for option in MODULE_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def register_course(
    service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    for line in format_title("Register Course"):
        output_func(line)
    output_func("Enter q at any prompt to cancel.")

    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Course registration cancelled.")
        output_func("")
        return

    course_name = _prompt_required("Enter course name: ", input_func, output_func)
    if course_name is None:
        output_func("Course registration cancelled.")
        output_func("")
        return

    description = _prompt_optional("Enter description (optional): ", input_func)
    if description == "q":
        output_func("Course registration cancelled.")
        output_func("")
        return

    fee_amount = _prompt_optional("Enter fee amount [0]: ", input_func)
    if fee_amount == "q":
        output_func("Course registration cancelled.")
        output_func("")
        return

    status = _prompt_status(
        "Enter status [planned/active/completed/archived] (blank for planned): ",
        COURSE_STATUSES,
        COURSE_PLANNED_STATUS,
        input_func,
        output_func,
    )
    if status is None:
        output_func("Course registration cancelled.")
        output_func("")
        return

    try:
        course = service.create_course(
            course_code=course_code,
            course_name=course_name,
            description=description,
            fee_amount=fee_amount,
            status=status,
        )
    except (ValidationError, DuplicateRecordError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Course registered successfully: {course.course_code}")

    output_func("")


def view_course(
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("View course cancelled.")
        output_func("")
        return

    try:
        course = course_service.get_course_by_code(course_code)
        modules = module_service.list_modules_for_course(
            course.course_code,
            include_archived=True,
        )
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_course_detail(course):
            output_func(line)
        output_func("")
        for line in format_module_table(
            modules,
            {_course_id(course): course.course_code},
            empty_message="No modules found for this course.",
        ):
            output_func(line)

    output_func("")


def list_courses(
    service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    filter_choice = _prompt_course_status_filter(input_func, output_func)
    if filter_choice is None:
        output_func("List courses cancelled.")
        output_func("")
        return

    include_archived, status = filter_choice
    try:
        courses = service.list_courses(
            include_archived=include_archived,
            status=status,
        )
    except (ValidationError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_course_table(courses):
            output_func(line)

    output_func("")


def search_courses(
    service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    search_text = _prompt_required("Enter search text: ", input_func, output_func)
    if search_text is None:
        output_func("Search courses cancelled.")
        output_func("")
        return

    filter_choice = _prompt_course_status_filter(input_func, output_func)
    if filter_choice is None:
        output_func("Search courses cancelled.")
        output_func("")
        return

    include_archived, status = filter_choice
    try:
        courses = service.search_courses(
            search_text,
            include_archived=include_archived,
            status=status,
        )
    except (ValidationError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_course_table(courses):
            output_func(line)

    output_func("")


def update_course(
    service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Update course cancelled.")
        output_func("")
        return

    try:
        current_course = service.get_course_by_code(course_code)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
        output_func("")
        return

    for line in format_course_detail(current_course):
        output_func(line)

    output_func("Course code cannot be changed.")
    output_func("Leave blank to keep the current value.")
    output_func("Enter - to clear the description.")

    course_name = _prompt_update_value(
        "Enter course name",
        current_course.course_name,
        input_func,
    )
    if course_name == "q":
        output_func("Update course cancelled.")
        output_func("")
        return

    description = _prompt_update_optional_value(
        "Enter description",
        current_course.description,
        input_func,
    )
    if description == "q":
        output_func("Update course cancelled.")
        output_func("")
        return

    fee_amount = _prompt_update_value(
        "Enter fee amount",
        _format_decimal(current_course.fee_amount),
        input_func,
    )
    if fee_amount == "q":
        output_func("Update course cancelled.")
        output_func("")
        return

    status = _prompt_update_status(
        "Enter status",
        current_course.status,
        COURSE_STATUSES,
        input_func,
        output_func,
    )
    if status is None:
        output_func("Update course cancelled.")
        output_func("")
        return

    try:
        updated_course = service.update_course(
            course_code=current_course.course_code,
            course_name=course_name,
            description=description,
            fee_amount=fee_amount,
            status=status,
        )
    except (ValidationError, DuplicateRecordError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Course updated successfully: {updated_course.course_code}")

    output_func("")


def deactivate_course(
    service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Deactivate course cancelled.")
        output_func("")
        return

    if not _confirm("Deactivate this course? [y/N]: ", input_func, output_func):
        output_func("Deactivate course cancelled.")
        output_func("")
        return

    try:
        course = service.deactivate_course(course_code)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Course is now archived: {course.course_code}")

    output_func("")


def reactivate_course(
    service: CourseService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Reactivate course cancelled.")
        output_func("")
        return

    if not _confirm("Reactivate this course? [y/N]: ", input_func, output_func):
        output_func("Reactivate course cancelled.")
        output_func("")
        return

    try:
        course = service.reactivate_course(course_code)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Course is now active: {course.course_code}")

    output_func("")


def add_module_to_course(
    service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    for line in format_title("Add Module to Course"):
        output_func(line)
    output_func("Enter q at any prompt to cancel.")

    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Module creation cancelled.")
        output_func("")
        return

    module_code = _prompt_required("Enter module code: ", input_func, output_func)
    if module_code is None:
        output_func("Module creation cancelled.")
        output_func("")
        return

    module_name = _prompt_required("Enter module name: ", input_func, output_func)
    if module_name is None:
        output_func("Module creation cancelled.")
        output_func("")
        return

    sequence_number = _prompt_required("Enter sequence number: ", input_func, output_func)
    if sequence_number is None:
        output_func("Module creation cancelled.")
        output_func("")
        return

    status = _prompt_status(
        "Enter status [active/archived] (blank for active): ",
        MODULE_STATUSES,
        MODULE_ACTIVE_STATUS,
        input_func,
        output_func,
    )
    if status is None:
        output_func("Module creation cancelled.")
        output_func("")
        return

    try:
        module = service.create_module(
            course_code=course_code,
            module_code=module_code,
            module_name=module_name,
            sequence_number=sequence_number,
            status=status,
        )
    except (
        ValidationError,
        DuplicateRecordError,
        RecordNotFoundError,
        DatabaseError,
    ) as error:
        output_func(str(error))
    else:
        output_func(f"Module created successfully: {module.module_code}")

    output_func("")


def view_module(
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("View module cancelled.")
        output_func("")
        return

    module_code = _prompt_required("Enter module code: ", input_func, output_func)
    if module_code is None:
        output_func("View module cancelled.")
        output_func("")
        return

    try:
        course = course_service.get_course_by_code(course_code)
        module = module_service.get_module(course.course_code, module_code)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_module_detail(module, course):
            output_func(line)

    output_func("")


def list_modules_for_course(
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("List modules cancelled.")
        output_func("")
        return

    filter_choice = _prompt_module_status_filter(input_func, output_func)
    if filter_choice is None:
        output_func("List modules cancelled.")
        output_func("")
        return

    include_archived, status = filter_choice
    try:
        course = course_service.get_course_by_code(course_code)
        modules = module_service.list_modules_for_course(
            course.course_code,
            include_archived=include_archived,
            status=status,
        )
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_module_table(
            modules,
            {_course_id(course): course.course_code},
            empty_message="No modules found for this course.",
        ):
            output_func(line)

    output_func("")


def search_modules(
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    search_text = _prompt_required("Enter search text: ", input_func, output_func)
    if search_text is None:
        output_func("Search modules cancelled.")
        output_func("")
        return

    course_code = _prompt_optional("Restrict to course code (optional): ", input_func)
    if course_code == "q":
        output_func("Search modules cancelled.")
        output_func("")
        return

    filter_choice = _prompt_module_status_filter(input_func, output_func)
    if filter_choice is None:
        output_func("Search modules cancelled.")
        output_func("")
        return

    include_archived, status = filter_choice
    try:
        modules = module_service.search_modules(
            search_text,
            course_code=course_code,
            include_archived=include_archived,
            status=status,
        )
        course_labels = _course_labels_for_modules(course_service, modules)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        empty_message = "No modules found."
        if course_code:
            empty_message = "No modules found for this course."
        for line in format_module_table(
            modules,
            course_labels,
            empty_message=empty_message,
        ):
            output_func(line)

    output_func("")


def update_module(
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Update module cancelled.")
        output_func("")
        return

    module_code = _prompt_required("Enter module code: ", input_func, output_func)
    if module_code is None:
        output_func("Update module cancelled.")
        output_func("")
        return

    try:
        course = course_service.get_course_by_code(course_code)
        current_module = module_service.get_module(course.course_code, module_code)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
        output_func("")
        return

    for line in format_module_detail(current_module, course):
        output_func(line)

    output_func("Course code and module code cannot be changed.")
    output_func("Leave blank to keep the current value.")

    module_name = _prompt_update_value(
        "Enter module name",
        current_module.module_name,
        input_func,
    )
    if module_name == "q":
        output_func("Update module cancelled.")
        output_func("")
        return

    sequence_number = _prompt_update_value(
        "Enter sequence number",
        str(current_module.sequence_number),
        input_func,
    )
    if sequence_number == "q":
        output_func("Update module cancelled.")
        output_func("")
        return

    status = _prompt_update_status(
        "Enter status",
        current_module.status,
        MODULE_STATUSES,
        input_func,
        output_func,
    )
    if status is None:
        output_func("Update module cancelled.")
        output_func("")
        return

    try:
        updated_module = module_service.update_module(
            course_code=course.course_code,
            module_code=current_module.module_code,
            module_name=module_name,
            sequence_number=sequence_number,
            status=status,
        )
    except (ValidationError, DuplicateRecordError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Module updated successfully: {updated_module.module_code}")

    output_func("")


def deactivate_module(
    service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Deactivate module cancelled.")
        output_func("")
        return

    module_code = _prompt_required("Enter module code: ", input_func, output_func)
    if module_code is None:
        output_func("Deactivate module cancelled.")
        output_func("")
        return

    if not _confirm("Deactivate this module? [y/N]: ", input_func, output_func):
        output_func("Deactivate module cancelled.")
        output_func("")
        return

    try:
        module = service.deactivate_module(course_code, module_code)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Module is now archived: {module.module_code}")

    output_func("")


def reactivate_module(
    service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Reactivate module cancelled.")
        output_func("")
        return

    module_code = _prompt_required("Enter module code: ", input_func, output_func)
    if module_code is None:
        output_func("Reactivate module cancelled.")
        output_func("")
        return

    if not _confirm("Reactivate this module? [y/N]: ", input_func, output_func):
        output_func("Reactivate module cancelled.")
        output_func("")
        return

    try:
        module = service.reactivate_module(course_code, module_code)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Module is now active: {module.module_code}")

    output_func("")


def format_course_detail(course: Course) -> list[str]:
    """Return a compact one-course display."""
    lines = format_title("Course Details")
    lines.extend(
        [
            f"{'Course code':<16}: {course.course_code}",
            f"{'Course name':<16}: {course.course_name}",
            f"{'Description':<16}: {course.description or '-'}",
            f"{'Fee amount':<16}: {_format_decimal(course.fee_amount)}",
            f"{'Status':<16}: {format_status(course.status)}",
            f"{'Created':<16}: {course.created_at}",
            f"{'Updated':<16}: {course.updated_at}",
        ]
    )
    return lines


def format_course_table(courses: list[Course]) -> list[str]:
    """Return an aligned course table or a useful empty-state line."""
    if not courses:
        return ["No courses found."]

    lines = [
        f"{'Course Code':<14} {'Course Name':<34} {'Status':<10} {'Fee'}",
        "-" * 76,
    ]
    for course in courses:
        lines.append(
            f"{course.course_code:<14} "
            f"{course.course_name:<34} "
            f"{format_status(course.status):<10} "
            f"{_format_decimal(course.fee_amount)}"
        )

    return lines


def format_module_detail(module: Module, course: Course) -> list[str]:
    """Return a compact one-module display with parent course context."""
    lines = format_title("Module Details")
    lines.extend(
        [
            f"{'Course':<16}: {_course_label(course)}",
            f"{'Module code':<16}: {module.module_code}",
            f"{'Module name':<16}: {module.module_name}",
            f"{'Sequence':<16}: {module.sequence_number}",
            f"{'Status':<16}: {format_status(module.status)}",
        ]
    )
    return lines


def format_module_table(
    modules: list[Module],
    course_labels: dict[int, str] | None = None,
    empty_message: str = "No modules found.",
) -> list[str]:
    """Return an aligned module table with parent course context."""
    if not modules:
        return [empty_message]

    labels = course_labels or {}
    lines = [
        f"{'Course Code':<14} {'Module Code':<12} {'Seq':<3} {'Status':<8} {'Module Name'}",
        "-" * 76,
    ]
    for module in modules:
        course_label = labels.get(module.course_id, f"Course ID {module.course_id}")
        lines.append(
            f"{course_label:<14} "
            f"{module.module_code:<12} "
            f"{module.sequence_number:<3} "
            f"{format_status(module.status):<8} "
            f"{module.module_name}"
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


def _prompt_status(
    prompt: str,
    allowed_statuses: tuple[str, ...],
    default_status: str,
    input_func,
    output_func,
) -> str | None:
    while True:
        value = _read_text(prompt, input_func).strip().lower()
        if _is_cancel(value):
            return None
        if not value:
            return default_status
        if value in allowed_statuses:
            return value
        output_func(f"Choose one of: {', '.join(allowed_statuses)}.")


def _prompt_update_status(
    prompt: str,
    current_status: str,
    allowed_statuses: tuple[str, ...],
    input_func,
    output_func,
) -> str | None:
    while True:
        value = _read_text(f"{prompt} [{current_status}]: ", input_func).strip().lower()
        if _is_cancel(value):
            return None
        if not value:
            return current_status
        if value in allowed_statuses:
            return value
        output_func(f"Choose one of: {', '.join(allowed_statuses)}.")


def _prompt_course_status_filter(input_func, output_func) -> tuple[bool, str | None] | None:
    prompt = (
        "Filter by status [planned/active/completed/archived/all] "
        "(blank for non-archived): "
    )
    return _prompt_status_filter(prompt, COURSE_STATUSES, input_func, output_func)


def _prompt_module_status_filter(input_func, output_func) -> tuple[bool, str | None] | None:
    prompt = "Filter by status [active/archived/all] (blank for active): "
    return _prompt_status_filter(prompt, MODULE_STATUSES, input_func, output_func)


def _prompt_status_filter(
    prompt: str,
    allowed_statuses: tuple[str, ...],
    input_func,
    output_func,
) -> tuple[bool, str | None] | None:
    while True:
        value = _read_text(prompt, input_func).strip().lower()
        if _is_cancel(value):
            return None
        if not value:
            return False, None
        if value == "all":
            return True, None
        if value in allowed_statuses:
            return value == "archived", value
        output_func(f"Choose one of: {', '.join((*allowed_statuses, 'all'))}.")


def _prompt_yes_no(prompt: str, input_func, output_func, default: bool) -> bool | None:
    return prompt_yes_no(prompt, input_func, output_func, default)


def _confirm(prompt: str, input_func, output_func) -> bool:
    return confirm(prompt, input_func, output_func)


def _read_text(prompt: str, input_func) -> str:
    return read_text(prompt, input_func)


def _is_cancel(value: str) -> bool:
    return is_cancel(value)


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")


def _course_label(course: Course) -> str:
    return f"{course.course_code} - {course.course_name}"


def _course_id(course: Course) -> int:
    return course.course_id


def _course_labels_for_modules(
    course_service: CourseService,
    modules: list[Module],
) -> dict[int, str]:
    labels = {}
    for module in modules:
        if module.course_id in labels:
            continue
        try:
            course = course_service.get_course_by_id(module.course_id)
        except (RecordNotFoundError, DatabaseError):
            labels[module.course_id] = f"Course ID {module.course_id}"
        else:
            labels[module.course_id] = course.course_code

    return labels
