"""Assessments and Marks command-line screens."""

from dataclasses import dataclass
from decimal import Decimal

from ..config.settings import AppConfig
from ..models.assessment import ASSESSMENT_STATUSES, ASSESSMENT_TYPES, Assessment
from ..models.mark import AssessmentResult, AssessmentSummary, MarkCaptureEntry
from ..models.module import Module
from ..models.student import Student
from ..services.assessment_service import (
    AssessmentService,
    round_percentage_for_display,
)
from ..services.course_service import CourseService
from ..services.module_service import ModuleService
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


_KEEP = object()
_CLEAR = object()


@dataclass(frozen=True)
class AssessmentMenuOption:
    """A numbered Assessments and Marks menu option."""

    choice: str
    label: str


ASSESSMENT_MENU_OPTIONS = (
    AssessmentMenuOption("1", "Create Assessment"),
    AssessmentMenuOption("2", "View Assessment"),
    AssessmentMenuOption("3", "List / Search Assessments"),
    AssessmentMenuOption("4", "Update Assessment"),
    AssessmentMenuOption("5", "Capture Individual Mark"),
    AssessmentMenuOption("6", "Capture Class Marks"),
    AssessmentMenuOption("7", "Correct Existing Mark"),
    AssessmentMenuOption("8", "View Assessment Results"),
    AssessmentMenuOption("9", "View Student Result History"),
    AssessmentMenuOption("10", "Assessment Summary"),
    AssessmentMenuOption("11", "Archive Assessment"),
    AssessmentMenuOption("12", "Reactivate Assessment"),
    AssessmentMenuOption("0", "Back"),
)

VALID_ASSESSMENT_MENU_CHOICES = tuple(
    option.choice for option in ASSESSMENT_MENU_OPTIONS
)


def run_assessment_menu(
    config: AppConfig,
    input_func=input,
    output_func=print,
    assessment_service: AssessmentService | None = None,
    course_service: CourseService | None = None,
    module_service: ModuleService | None = None,
    student_service: StudentService | None = None,
) -> None:
    """Run the Assessments and Marks submenu."""
    assessments = assessment_service or AssessmentService(config.paths.database_path)
    courses = course_service or CourseService(config.paths.database_path)
    modules = module_service or ModuleService(config.paths.database_path)
    students = student_service or StudentService(config.paths.database_path)

    while True:
        show_assessment_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_ASSESSMENT_MENU_CHOICES):
            output_func("Choose a number from the Assessments and Marks menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Main Menu.")
            output_func("")
            return

        if choice == "1":
            create_assessment(assessments, input_func, output_func)
        elif choice == "2":
            view_assessment(assessments, courses, modules, input_func, output_func)
        elif choice == "3":
            list_assessments(assessments, courses, modules, input_func, output_func)
        elif choice == "4":
            update_assessment(assessments, courses, modules, input_func, output_func)
        elif choice == "5":
            capture_individual_mark(assessments, courses, modules, input_func, output_func)
        elif choice == "6":
            capture_class_marks(
                assessments,
                courses,
                modules,
                input_func,
                output_func,
            )
        elif choice == "7":
            correct_existing_mark(assessments, courses, modules, input_func, output_func)
        elif choice == "8":
            view_assessment_results(
                assessments,
                students,
                courses,
                modules,
                input_func,
                output_func,
            )
        elif choice == "9":
            view_student_result_history(
                assessments,
                courses,
                modules,
                input_func,
                output_func,
            )
        elif choice == "10":
            assessment_summary(assessments, courses, modules, input_func, output_func)
        elif choice == "11":
            archive_assessment(assessments, courses, modules, input_func, output_func)
        elif choice == "12":
            reactivate_assessment(assessments, courses, modules, input_func, output_func)


def show_assessment_menu(output_func=print) -> None:
    """Display the Assessments and Marks submenu."""
    for line in format_title("Assessments and Marks"):
        output_func(line)

    for option in ASSESSMENT_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def create_assessment(
    service: AssessmentService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    for line in format_title("Create Assessment"):
        output_func(line)
    output_func("Enter q at any prompt to cancel.")

    course_code = _prompt_required("Enter course code: ", input_func, output_func)
    if course_code is None:
        output_func("Assessment creation cancelled.")
        output_func("")
        return

    module_code = _prompt_optional("Enter module code (optional): ", input_func)
    if module_code == "q":
        output_func("Assessment creation cancelled.")
        output_func("")
        return

    assessment_name = _prompt_required(
        "Enter assessment name: ",
        input_func,
        output_func,
    )
    if assessment_name is None:
        output_func("Assessment creation cancelled.")
        output_func("")
        return

    assessment_type = _prompt_assessment_type(input_func, output_func)
    if assessment_type is None:
        output_func("Assessment creation cancelled.")
        output_func("")
        return

    max_mark = _prompt_required("Enter maximum mark: ", input_func, output_func)
    if max_mark is None:
        output_func("Assessment creation cancelled.")
        output_func("")
        return

    weight = _prompt_optional("Enter weight (optional): ", input_func)
    if weight == "q":
        output_func("Assessment creation cancelled.")
        output_func("")
        return

    pass_mark = _prompt_optional("Enter pass mark (optional): ", input_func)
    if pass_mark == "q":
        output_func("Assessment creation cancelled.")
        output_func("")
        return

    status = _prompt_assessment_status(input_func, output_func, default="active")
    if status is None:
        output_func("Assessment creation cancelled.")
        output_func("")
        return

    try:
        assessment = service.create_assessment(
            course_code=course_code,
            module_code=module_code,
            assessment_name=assessment_name,
            assessment_type=assessment_type,
            max_mark=max_mark,
            weight=weight,
            pass_mark=pass_mark,
            status=status,
        )
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Assessment created successfully: ID {assessment.assessment_id}")

    output_func("")


def view_assessment(
    assessment_service: AssessmentService,
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_assessment_selection_context(
        assessment_service,
        course_service,
        module_service,
        output_func,
    )
    assessment_id = _prompt_required("Enter assessment ID: ", input_func, output_func)
    if assessment_id is None:
        output_func("View assessment cancelled.")
        output_func("")
        return

    try:
        assessment = assessment_service.get_assessment(assessment_id)
        course = course_service.get_course_by_id(assessment.course_id)
        module = _get_module_for_display(module_service, assessment)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_assessment_detail(assessment, course.course_code, module):
            output_func(line)

    output_func("")


def list_assessments(
    assessment_service: AssessmentService,
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    search_text = _prompt_optional("Search text (optional): ", input_func)
    if search_text == "q":
        output_func("List assessments cancelled.")
        output_func("")
        return

    course_code = _prompt_optional("Course code filter (optional): ", input_func)
    if course_code == "q":
        output_func("List assessments cancelled.")
        output_func("")
        return

    module_code = _prompt_optional("Module code filter (optional): ", input_func)
    if module_code == "q":
        output_func("List assessments cancelled.")
        output_func("")
        return

    assessment_type = _prompt_optional("Type filter (optional): ", input_func)
    if assessment_type == "q":
        output_func("List assessments cancelled.")
        output_func("")
        return

    status = _prompt_optional("Status filter (optional): ", input_func)
    if status == "q":
        output_func("List assessments cancelled.")
        output_func("")
        return

    include_archived = _prompt_yes_no(
        "Include archived assessments? [y/N]: ",
        input_func,
        output_func,
        default=False,
    )
    if include_archived is None:
        output_func("List assessments cancelled.")
        output_func("")
        return

    try:
        if search_text:
            assessments = assessment_service.search_assessments(
                search_text=search_text,
                course_code=course_code,
                module_code=module_code,
                include_archived=include_archived,
                status=status,
                assessment_type=assessment_type,
            )
        else:
            assessments = assessment_service.list_assessments(
                course_code=course_code,
                module_code=module_code,
                include_archived=include_archived,
                status=status,
                assessment_type=assessment_type,
            )
        course_labels = _course_labels_for_assessments(course_service, assessments)
        module_labels = _module_labels_for_assessments(module_service, assessments)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_assessment_table(assessments, course_labels, module_labels):
            output_func(line)

    output_func("")


def update_assessment(
    assessment_service: AssessmentService,
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_assessment_selection_context(
        assessment_service,
        course_service,
        module_service,
        output_func,
    )
    assessment_id = _prompt_required("Enter assessment ID: ", input_func, output_func)
    if assessment_id is None:
        output_func("Update assessment cancelled.")
        output_func("")
        return

    try:
        current = assessment_service.get_assessment(assessment_id)
        course = course_service.get_course_by_id(current.course_id)
        module = _get_module_for_display(module_service, current)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
        output_func("")
        return

    for line in format_assessment_detail(current, course.course_code, module):
        output_func(line)
    output_func("Leave blank to keep the current value. Enter - to clear optional marks.")

    name = _prompt_update_required_value(
        "Enter assessment name",
        current.assessment_name,
        input_func,
    )
    if name == "q":
        output_func("Update assessment cancelled.")
        output_func("")
        return

    assessment_type = _prompt_update_required_value(
        "Enter assessment type",
        current.assessment_type,
        input_func,
    )
    if assessment_type == "q":
        output_func("Update assessment cancelled.")
        output_func("")
        return

    max_mark = _prompt_update_required_value(
        "Enter maximum mark",
        _format_decimal(current.max_mark),
        input_func,
    )
    if max_mark == "q":
        output_func("Update assessment cancelled.")
        output_func("")
        return

    weight = _prompt_update_optional_value(
        "Enter weight",
        current.weight,
        input_func,
    )
    if weight == "q":
        output_func("Update assessment cancelled.")
        output_func("")
        return

    pass_mark = _prompt_update_optional_value(
        "Enter pass mark",
        current.pass_mark,
        input_func,
    )
    if pass_mark == "q":
        output_func("Update assessment cancelled.")
        output_func("")
        return

    status = _prompt_update_required_value(
        "Enter status",
        current.status,
        input_func,
    )
    if status == "q":
        output_func("Update assessment cancelled.")
        output_func("")
        return

    update_kwargs = {
        "assessment_id": current.assessment_id,
        "assessment_name": None if name is _KEEP else name,
        "assessment_type": None if assessment_type is _KEEP else assessment_type,
        "max_mark": None if max_mark is _KEEP else max_mark,
        "status": None if status is _KEEP else status,
    }
    if weight is not _KEEP:
        update_kwargs["weight"] = None if weight is _CLEAR else weight
    if pass_mark is not _KEEP:
        update_kwargs["pass_mark"] = None if pass_mark is _CLEAR else pass_mark

    try:
        updated = assessment_service.update_assessment(**update_kwargs)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Assessment updated successfully: ID {updated.assessment_id}")

    output_func("")


def capture_individual_mark(
    service: AssessmentService,
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    for line in format_title("Capture Individual Mark"):
        output_func(line)
    output_func("Enter q at any prompt to cancel.")
    _show_assessment_selection_context(service, course_service, module_service, output_func)

    assessment_id = _prompt_required("Enter assessment ID: ", input_func, output_func)
    if assessment_id is None:
        output_func("Mark capture cancelled.")
        output_func("")
        return

    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Mark capture cancelled.")
        output_func("")
        return

    mark_obtained = _prompt_required("Enter mark obtained: ", input_func, output_func)
    if mark_obtained is None:
        output_func("Mark capture cancelled.")
        output_func("")
        return

    notes = _prompt_optional("Enter notes (optional): ", input_func)
    if notes == "q":
        output_func("Mark capture cancelled.")
        output_func("")
        return

    try:
        mark = service.record_mark(
            assessment_id=assessment_id,
            student_number=student_number,
            mark_obtained=mark_obtained,
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
        output_func(f"Mark captured successfully: ID {mark.mark_id}")

    output_func("")


def capture_class_marks(
    assessment_service: AssessmentService,
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_assessment_selection_context(
        assessment_service,
        course_service,
        module_service,
        output_func,
    )
    assessment_id = _prompt_required("Enter assessment ID: ", input_func, output_func)
    if assessment_id is None:
        output_func("Class mark capture cancelled.")
        output_func("")
        return

    try:
        assessment = assessment_service.get_assessment(assessment_id)
        course = course_service.get_course_by_id(assessment.course_id)
        module = _get_module_for_display(module_service, assessment)
        students = assessment_service.list_eligible_students(assessment.assessment_id)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
        output_func("")
        return

    for line in format_assessment_detail(assessment, course.course_code, module):
        output_func(line)

    if not students:
        output_func("No eligible students found for this assessment.")
        output_func("")
        return

    output_func("Enter q at any prompt to cancel. Leave a mark blank to skip a student.")
    entries = []
    for student in students:
        mark_obtained = _prompt_optional(
            f"Mark for {student.student_number} {student.full_name} (blank to skip): ",
            input_func,
        )
        if mark_obtained == "q":
            output_func("Class mark capture cancelled.")
            output_func("")
            return
        if mark_obtained is None:
            continue

        notes = _prompt_optional(
            f"Notes for {student.student_number} (optional): ",
            input_func,
        )
        if notes == "q":
            output_func("Class mark capture cancelled.")
            output_func("")
            return

        entries.append(
            MarkCaptureEntry(
                student_number=student.student_number,
                mark_obtained=mark_obtained,
                notes=notes,
            )
        )

    if not entries:
        output_func("No class marks entered.")
        output_func("")
        return

    if not _confirm("Save these class marks? [y/N]: ", input_func, output_func):
        output_func("Class mark capture cancelled.")
        output_func("")
        return

    try:
        marks = assessment_service.record_class_marks(assessment.assessment_id, entries)
    except (
        ValidationError,
        DuplicateRecordError,
        RecordNotFoundError,
        DatabaseError,
    ) as error:
        output_func(str(error))
    else:
        output_func(f"Class marks captured successfully: {len(marks)} records")

    output_func("")


def correct_existing_mark(
    service: AssessmentService,
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_assessment_selection_context(service, course_service, module_service, output_func)
    assessment_id = _prompt_required("Enter assessment ID: ", input_func, output_func)
    if assessment_id is None:
        output_func("Mark correction cancelled.")
        output_func("")
        return

    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("Mark correction cancelled.")
        output_func("")
        return

    try:
        current = service.get_mark(assessment_id, student_number)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
        output_func("")
        return

    output_func(f"Current mark: {_format_decimal(current.mark_obtained)}")
    output_func(f"Current notes: {current.notes or '-'}")

    corrected_mark = _prompt_required("Enter corrected mark: ", input_func, output_func)
    if corrected_mark is None:
        output_func("Mark correction cancelled.")
        output_func("")
        return

    notes = _prompt_update_optional_text("Enter notes", current.notes, input_func)
    if notes == "q":
        output_func("Mark correction cancelled.")
        output_func("")
        return

    try:
        updated = service.correct_mark(
            assessment_id=assessment_id,
            student_number=student_number,
            mark_obtained=corrected_mark,
            notes=None if notes is _CLEAR else notes,
        )
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Mark corrected successfully: ID {updated.mark_id}")

    output_func("")


def view_assessment_results(
    assessment_service: AssessmentService,
    student_service: StudentService,
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_assessment_selection_context(
        assessment_service,
        course_service,
        module_service,
        output_func,
    )
    assessment_id = _prompt_required("Enter assessment ID: ", input_func, output_func)
    if assessment_id is None:
        output_func("View assessment results cancelled.")
        output_func("")
        return

    try:
        results = assessment_service.list_assessment_results(assessment_id)
        student_labels = _student_labels_for_results(student_service, results)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_assessment_results_table(results, student_labels):
            output_func(line)

    output_func("")


def view_student_result_history(
    assessment_service: AssessmentService,
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    student_number = _prompt_required("Enter student number: ", input_func, output_func)
    if student_number is None:
        output_func("View student result history cancelled.")
        output_func("")
        return

    course_code = _prompt_optional("Course code filter (optional): ", input_func)
    if course_code == "q":
        output_func("View student result history cancelled.")
        output_func("")
        return

    try:
        results = assessment_service.list_student_result_history(
            student_number=student_number,
            course_code=course_code,
        )
        course_labels = _course_labels_for_results(course_service, results)
        module_labels = _module_labels_for_results(module_service, results)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_student_result_history_table(
            results,
            course_labels,
            module_labels,
        ):
            output_func(line)

    output_func("")


def assessment_summary(
    service: AssessmentService,
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_assessment_selection_context(service, course_service, module_service, output_func)
    assessment_id = _prompt_required("Enter assessment ID: ", input_func, output_func)
    if assessment_id is None:
        output_func("Assessment summary cancelled.")
        output_func("")
        return

    try:
        assessment = service.get_assessment(assessment_id)
        summary = service.calculate_assessment_summary(assessment_id)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        for line in format_assessment_summary(summary, assessment):
            output_func(line)

    output_func("")


def archive_assessment(
    service: AssessmentService,
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_assessment_selection_context(service, course_service, module_service, output_func)
    assessment_id = _prompt_required("Enter assessment ID: ", input_func, output_func)
    if assessment_id is None:
        output_func("Archive assessment cancelled.")
        output_func("")
        return

    if not _confirm("Archive this assessment? [y/N]: ", input_func, output_func):
        output_func("Archive assessment cancelled.")
        output_func("")
        return

    try:
        assessment = service.deactivate_assessment(assessment_id)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Assessment archived successfully: ID {assessment.assessment_id}")

    output_func("")


def reactivate_assessment(
    service: AssessmentService,
    course_service: CourseService,
    module_service: ModuleService,
    input_func=input,
    output_func=print,
) -> None:
    output_func("")
    _show_assessment_selection_context(service, course_service, module_service, output_func)
    assessment_id = _prompt_required("Enter assessment ID: ", input_func, output_func)
    if assessment_id is None:
        output_func("Reactivate assessment cancelled.")
        output_func("")
        return

    try:
        assessment = service.reactivate_assessment(assessment_id)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
    else:
        output_func(f"Assessment reactivated successfully: ID {assessment.assessment_id}")

    output_func("")


def format_assessment_detail(
    assessment: Assessment,
    course_label: str,
    module: Module | None,
) -> list[str]:
    """Return a compact assessment display."""
    lines = format_title("Assessment Details")
    lines.extend(
        [
            f"{'Assessment ID':<16}: {assessment.assessment_id}",
            f"{'Name':<16}: {assessment.assessment_name}",
            f"{'Type':<16}: {assessment.assessment_type}",
            f"{'Course':<16}: {course_label}",
            f"{'Module':<16}: {_module_label(module)}",
            f"{'Maximum mark':<16}: {_format_decimal(assessment.max_mark)}",
            f"{'Weight':<16}: {_format_optional_decimal(assessment.weight)}",
            f"{'Pass mark':<16}: {_format_optional_decimal(assessment.pass_mark)}",
            f"{'Status':<16}: {format_status(assessment.status)}",
            f"{'Created':<16}: {assessment.created_at}",
            f"{'Updated':<16}: {assessment.updated_at}",
        ]
    )
    return lines


def format_assessment_table(
    assessments: list[Assessment],
    course_labels: dict[int, str] | None = None,
    module_labels: dict[int, str] | None = None,
) -> list[str]:
    """Return an aligned assessment table."""
    if not assessments:
        return ["No assessments found."]

    courses = course_labels or {}
    modules = module_labels or {}
    lines = [
        f"{'ID':<4} {'Course':<12} {'Module':<16} {'Type':<10} "
        f"{'Max':<8} {'Pass':<8} {'Status':<8} Name",
        "-" * 96,
    ]
    for assessment in assessments:
        module_label = "Course level"
        if assessment.module_id is not None:
            module_label = modules.get(
                assessment.module_id,
                f"Module {assessment.module_id}",
            )
        lines.append(
            f"{assessment.assessment_id:<4} "
            f"{courses.get(assessment.course_id, f'Course {assessment.course_id}'):<12} "
            f"{module_label:<16} "
            f"{assessment.assessment_type:<10} "
            f"{_format_decimal(assessment.max_mark):<8} "
            f"{_format_optional_decimal(assessment.pass_mark):<8} "
            f"{format_status(assessment.status):<8} "
            f"{assessment.assessment_name}"
        )

    return lines


def format_assessment_results_table(
    results: list[AssessmentResult],
    student_labels: dict[int, str] | None = None,
) -> list[str]:
    """Return an aligned assessment result table."""
    if not results:
        return ["No marks recorded for this assessment."]

    students = student_labels or {}
    assessment = results[0].assessment
    lines = [
        f"{'Mark':<5} {'Student':<30} {'Score':<10} {'Max':<8} "
        f"{'Percent':<9} Result",
        "-" * 82,
    ]
    for result in results:
        mark = result.mark
        lines.append(
            f"{mark.mark_id:<5} "
            f"{students.get(mark.student_id, f'Student {mark.student_id}'):<30} "
            f"{_format_decimal(mark.mark_obtained):<10} "
            f"{_format_decimal(assessment.max_mark):<8} "
            f"{_format_percentage(result.percentage):<9} "
            f"{_format_result_state(result.result_state)}"
        )

    return lines


def format_student_result_history_table(
    results: list[AssessmentResult],
    course_labels: dict[int, str] | None = None,
    module_labels: dict[int, str] | None = None,
) -> list[str]:
    """Return an aligned student result history table."""
    if not results:
        return ["No assessment results found for this student."]

    courses = course_labels or {}
    modules = module_labels or {}
    lines = [
        f"{'Course':<12} {'Module':<16} {'Assessment':<24} {'Score':<10} "
        f"{'Percent':<9} {'Result':<11} Date",
        "-" * 100,
    ]
    for result in results:
        assessment = result.assessment
        module_label = "Course level"
        if assessment.module_id is not None:
            module_label = modules.get(
                assessment.module_id,
                f"Module {assessment.module_id}",
            )
        lines.append(
            f"{courses.get(assessment.course_id, f'Course {assessment.course_id}'):<12} "
            f"{module_label:<16} "
            f"{assessment.assessment_name:<24} "
            f"{_format_decimal(result.mark.mark_obtained):<10} "
            f"{_format_percentage(result.percentage):<9} "
            f"{_format_result_state(result.result_state):<11} "
            f"{result.mark.captured_at}"
        )

    return lines


def format_assessment_summary(
    summary: AssessmentSummary,
    assessment: Assessment,
) -> list[str]:
    """Return a compact assessment summary display."""
    lines = format_title("Assessment Summary")
    lines.extend(
        [
            f"{'Assessment ID':<22}: {summary.assessment_id}",
            f"{'Assessment':<22}: {assessment.assessment_name}",
            f"{'Recorded results':<22}: {summary.recorded_count}",
            f"{'Average mark':<22}: {_format_optional_decimal(summary.average_mark)}",
            f"{'Average percentage':<22}: {_format_optional_percentage(summary.average_percentage)}",
            f"{'Highest mark':<22}: {_format_optional_decimal(summary.highest_mark)}",
            f"{'Lowest mark':<22}: {_format_optional_decimal(summary.lowest_mark)}",
        ]
    )

    if summary.has_pass_fail_counts:
        lines.extend(
            [
                f"{'Pass count':<22}: {summary.pass_count}",
                f"{'Fail count':<22}: {summary.fail_count}",
                f"{'Pass rate':<22}: {_format_optional_percentage(summary.pass_rate)}",
            ]
        )
    else:
        lines.append(f"{'Pass/fail':<22}: Not defined")

    return lines


def _course_labels_for_assessments(
    course_service: CourseService,
    assessments: list[Assessment],
) -> dict[int, str]:
    labels = {}
    for assessment in assessments:
        if assessment.course_id in labels:
            continue
        try:
            labels[assessment.course_id] = course_service.get_course_by_id(
                assessment.course_id
            ).course_code
        except (RecordNotFoundError, DatabaseError):
            labels[assessment.course_id] = f"Course {assessment.course_id}"

    return labels


def _module_labels_for_assessments(
    module_service: ModuleService,
    assessments: list[Assessment],
) -> dict[int, str]:
    labels = {}
    for assessment in assessments:
        if assessment.module_id is None or assessment.module_id in labels:
            continue
        try:
            labels[assessment.module_id] = _module_label(
                module_service.get_module_by_id(assessment.module_id)
            )
        except (RecordNotFoundError, DatabaseError):
            labels[assessment.module_id] = f"Module {assessment.module_id}"

    return labels


def _student_labels_for_results(
    student_service: StudentService,
    results: list[AssessmentResult],
) -> dict[int, str]:
    labels = {}
    for result in results:
        student_id = result.mark.student_id
        if student_id in labels:
            continue
        try:
            labels[student_id] = _student_label(student_service.get_student_by_id(student_id))
        except (RecordNotFoundError, DatabaseError):
            labels[student_id] = f"Student {student_id}"

    return labels


def _course_labels_for_results(
    course_service: CourseService,
    results: list[AssessmentResult],
) -> dict[int, str]:
    return _course_labels_for_assessments(
        course_service,
        [result.assessment for result in results],
    )


def _module_labels_for_results(
    module_service: ModuleService,
    results: list[AssessmentResult],
) -> dict[int, str]:
    return _module_labels_for_assessments(
        module_service,
        [result.assessment for result in results],
    )


def _get_module_for_display(
    module_service: ModuleService,
    assessment: Assessment,
) -> Module | None:
    if assessment.module_id is None:
        return None

    return module_service.get_module_by_id(assessment.module_id)


def _student_label(student: Student) -> str:
    return f"{student.student_number} {student.full_name}"


def _module_label(module: Module | None) -> str:
    if module is None:
        return "Course level"

    return f"{module.module_code} - {module.module_name}"


def _format_allowed_types() -> str:
    return "/".join(ASSESSMENT_TYPES)


def _format_allowed_statuses() -> str:
    return "/".join(ASSESSMENT_STATUSES)


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _format_optional_decimal(value: Decimal | None) -> str:
    if value is None:
        return "-"

    return _format_decimal(value)


def _format_percentage(value: Decimal) -> str:
    rounded = round_percentage_for_display(value)
    return f"{rounded:.2f}%"


def _format_optional_percentage(value: Decimal | None) -> str:
    if value is None:
        return "No results"

    return _format_percentage(value)


def _format_result_state(result_state: str | None) -> str:
    if result_state is None:
        return "Not defined"

    return format_status(result_state)


def _show_assessment_selection_context(
    assessment_service: AssessmentService,
    course_service: CourseService,
    module_service: ModuleService,
    output_func,
) -> None:
    try:
        assessments = assessment_service.list_assessments(include_archived=True)
        course_labels = _course_labels_for_assessments(course_service, assessments)
        module_labels = _module_labels_for_assessments(module_service, assessments)
    except (ValidationError, RecordNotFoundError, DatabaseError) as error:
        output_func(str(error))
        return

    output_func("Assessments:")
    for line in format_assessment_table(assessments, course_labels, module_labels):
        output_func(line)


def _prompt_required(prompt: str, input_func, output_func) -> str | None:
    if entered_value:
        return entered_value
    entered_value = prompt_required(prompt, input_func, output_func)
    return entered_value


def _prompt_optional(prompt: str, input_func) -> str | None:
    return prompt_optional(prompt, input_func)


def _prompt_assessment_type(input_func, output_func) -> str | None:
    prompt = f"Enter assessment type [{_format_allowed_types()}]: "
    while True:
        value = _read_text(prompt, input_func).strip().lower()
        if _is_cancel(value):
            return None
        if value in ASSESSMENT_TYPES:
            return value
        output_func(f"Choose one of: {', '.join(ASSESSMENT_TYPES)}.")


def _prompt_assessment_status(input_func, output_func, default: str) -> str | None:
    prompt = f"Enter status [{_format_allowed_statuses()}] (blank for {default}): "
    while True:
        value = _read_text(prompt, input_func).strip().lower()
        if _is_cancel(value):
            return None
        if not value:
            return default
        if value in ASSESSMENT_STATUSES:
            return value
        output_func(f"Choose one of: {', '.join(ASSESSMENT_STATUSES)}.")


def _prompt_update_required_value(prompt: str, current_value: str, input_func):
    value = _read_text(f"{prompt} [{current_value}]: ", input_func)
    if _is_cancel(value):
        return "q"

    return value.strip() or _KEEP


def _prompt_update_optional_value(
    prompt: str,
    current_value: Decimal | None,
    input_func,
):
    display_value = _format_optional_decimal(current_value)
    value = _read_text(f"{prompt} [{display_value}]: ", input_func)
    if _is_cancel(value):
        return "q"
    if value.strip() == "-":
        return _CLEAR

    return value.strip() or _KEEP


def _prompt_update_optional_text(prompt: str, current_value: str | None, input_func):
    display_value = current_value or "-"
    value = _read_text(f"{prompt} [{display_value}]: ", input_func)
    if _is_cancel(value):
        return "q"
    if value.strip() == "-":
        return _CLEAR

    return value.strip() or current_value


def _prompt_yes_no(prompt: str, input_func, output_func, default: bool) -> bool | None:
    return prompt_yes_no(prompt, input_func, output_func, default)


def _confirm(prompt: str, input_func, output_func) -> bool:
    return False


def _read_text(prompt: str, input_func) -> str:
    return read_text(prompt, input_func)


def _is_cancel(value: str) -> bool:
    return is_cancel(value)
