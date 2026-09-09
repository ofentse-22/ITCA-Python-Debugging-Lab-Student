"""Import / Export command-line screens."""

from dataclasses import dataclass

from ..config.settings import AppConfig
from ..models.import_export import (
    EXPORT_ASSESSMENTS,
    EXPORT_ATTENDANCE,
    EXPORT_COURSES,
    EXPORT_ENROLMENTS,
    EXPORT_MARKS,
    EXPORT_MODULES,
    EXPORT_STUDENTS,
    EXPORT_TRAINER_ASSIGNMENTS,
    EXPORT_TRAINERS,
    IMPORT_COURSES,
    IMPORT_ENROLMENTS,
    IMPORT_MODULES,
    IMPORT_STUDENTS,
    IMPORT_TRAINERS,
    REPORT_ASSESSMENT_PERFORMANCE,
    REPORT_ATTENDANCE,
    REPORT_COURSE_OVERVIEW,
    REPORT_LOW_ATTENDANCE,
    REPORT_STUDENT_PROGRESS,
    REPORT_SYSTEM_OVERVIEW,
    REPORT_TRAINER_ASSIGNMENT,
    ExportResult,
    ImportPreview,
)
from ..services.import_export_service import (
    IMPORT_LABELS,
    OPERATIONAL_EXPORT_LABELS,
    REPORT_EXPORT_LABELS,
    ImportExportService,
)
from ..utils import exceptions as ImportExportError
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    ExportFileError,
    RecordNotFoundError,
    ValidationError,
)
from .prompts import (
    confirm,
    is_cancel,
    is_valid_menu_choice,
    prompt_optional,
    prompt_required,
    read_menu_choice,
    read_text,
)
from .tables import format_title


DEFAULT_LOW_ATTENDANCE_THRESHOLD = "80"


@dataclass(frozen=True)
class ImportExportMenuOption:
    """A numbered Import / Export menu option."""

    choice: str
    label: str


IMPORT_EXPORT_MENU_OPTIONS = (
    ImportExportMenuOption("1", "Import Data"),
    ImportExportMenuOption("2", "Export Operational Data"),
    ImportExportMenuOption("3", "Export Reports"),
    ImportExportMenuOption("4", "View Recent Export Files"),
    ImportExportMenuOption("0", "Back"),
)

IMPORT_MENU_OPTIONS = (
    ImportExportMenuOption("1", "Students"),
    ImportExportMenuOption("2", "Courses"),
    ImportExportMenuOption("3", "Modules"),
    ImportExportMenuOption("4", "Trainers"),
    ImportExportMenuOption("5", "Enrolments"),
    ImportExportMenuOption("0", "Back"),
)

OPERATIONAL_EXPORT_MENU_OPTIONS = (
    ImportExportMenuOption("1", "Students"),
    ImportExportMenuOption("2", "Courses"),
    ImportExportMenuOption("3", "Modules"),
    ImportExportMenuOption("4", "Trainers"),
    ImportExportMenuOption("5", "Enrolments"),
    ImportExportMenuOption("6", "Trainer Assignments"),
    ImportExportMenuOption("7", "Attendance"),
    ImportExportMenuOption("8", "Assessments"),
    ImportExportMenuOption("9", "Marks / Results"),
    ImportExportMenuOption("0", "Back"),
)

REPORT_EXPORT_MENU_OPTIONS = (
    ImportExportMenuOption("1", "System Overview"),
    ImportExportMenuOption("2", "Student Progress Report"),
    ImportExportMenuOption("3", "Course Overview Report"),
    ImportExportMenuOption("4", "Attendance Report"),
    ImportExportMenuOption("5", "Low Attendance Students"),
    ImportExportMenuOption("6", "Assessment Performance Report"),
    ImportExportMenuOption("7", "Trainer Assignment Report"),
    ImportExportMenuOption("0", "Back"),
)

IMPORT_CHOICE_TO_TYPE = {
    "1": IMPORT_STUDENTS,
    "2": IMPORT_COURSES,
    "3": IMPORT_MODULES,
    "4": IMPORT_TRAINERS,
    "5": IMPORT_ENROLMENTS,
}

OPERATIONAL_EXPORT_CHOICE_TO_TYPE = {
    "1": EXPORT_STUDENTS,
    "2": EXPORT_COURSES,
    "3": EXPORT_MODULES,
    "4": EXPORT_TRAINERS,
    "5": EXPORT_ENROLMENTS,
    "6": EXPORT_TRAINER_ASSIGNMENTS,
    "7": EXPORT_ATTENDANCE,
    "8": EXPORT_ASSESSMENTS,
    "9": EXPORT_MARKS,
}

REPORT_EXPORT_CHOICE_TO_TYPE = {
    "1": REPORT_SYSTEM_OVERVIEW,
    "2": REPORT_STUDENT_PROGRESS,
    "3": REPORT_COURSE_OVERVIEW,
    "4": REPORT_ATTENDANCE,
    "5": REPORT_LOW_ATTENDANCE,
    "6": REPORT_ASSESSMENT_PERFORMANCE,
    "7": REPORT_TRAINER_ASSIGNMENT,
}

VALID_IMPORT_EXPORT_MENU_CHOICES = tuple(
    option.choice for option in IMPORT_EXPORT_MENU_OPTIONS
)
VALID_IMPORT_MENU_CHOICES = tuple(option.choice for option in IMPORT_MENU_OPTIONS)
VALID_OPERATIONAL_EXPORT_MENU_CHOICES = tuple(
    option.choice for option in OPERATIONAL_EXPORT_MENU_OPTIONS
)
VALID_REPORT_EXPORT_MENU_CHOICES = tuple(
    option.choice for option in REPORT_EXPORT_MENU_OPTIONS
)


def run_import_export_menu(
    config: AppConfig,
    input_func=input,
    output_func=print,
    service: ImportExportService | None = None,
) -> None:
    """Run the Import / Export submenu."""
    workflows = service or ImportExportService(
        database_path=config.paths.database_path,
        import_dir=config.paths.import_dir,
        export_dir=config.paths.export_dir,
    )

    while True:
        show_import_export_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_IMPORT_EXPORT_MENU_CHOICES):
            output_func("Choose a number from the Import / Export menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Main Menu.")
            output_func("")
            return
        if choice == "1":
            run_import_data_menu(workflows, input_func, output_func)
        elif choice == "2":
            run_operational_export_menu(config, workflows, input_func, output_func)
        elif choice == "3":
            run_report_export_menu(config, workflows, input_func, output_func)
        elif choice == "4":
            show_recent_exports(workflows, output_func)


def show_import_export_menu(output_func=print) -> None:
    """Display the Import / Export menu."""
    for line in format_title("IMPORT / EXPORT"):
        output_func(line)

    for option in IMPORT_EXPORT_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def run_import_data_menu(
    service: ImportExportService,
    input_func=input,
    output_func=print,
) -> None:
    """Run import-data options and confirmed import flow."""
    while True:
        show_import_data_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_IMPORT_MENU_CHOICES):
            output_func("Choose a number from the Import Data menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Import / Export.")
            output_func("")
            return

        import_type = IMPORT_CHOICE_TO_TYPE[choice]
        _run_import_flow(service, import_type, input_func, output_func)


def show_import_data_menu(output_func=print) -> None:
    """Display implemented import types."""
    for line in format_title("IMPORT DATA"):
        output_func(line)

    for option in IMPORT_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def run_operational_export_menu(
    config: AppConfig,
    service: ImportExportService,
    input_func=input,
    output_func=print,
) -> None:
    """Run operational data export options."""
    while True:
        show_operational_export_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_OPERATIONAL_EXPORT_MENU_CHOICES):
            output_func("Choose a number from the Export Operational Data menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Import / Export.")
            output_func("")
            return

        export_type = OPERATIONAL_EXPORT_CHOICE_TO_TYPE[choice]
        try:
            result = service.export_operational_data(export_type)
        except (ValidationError, DatabaseError, ExportFileError) as error:
            output_func(str(error))
            output_func("")
        else:
            _display_export_result(config, result, output_func)


def show_operational_export_menu(output_func=print) -> None:
    """Display implemented operational export types."""
    for line in format_title("EXPORT OPERATIONAL DATA"):
        output_func(line)

    for option in OPERATIONAL_EXPORT_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def run_report_export_menu(
    config: AppConfig,
    service: ImportExportService,
    input_func=input,
    output_func=print,
) -> None:
    """Run report export options."""
    while True:
        show_report_export_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_REPORT_EXPORT_MENU_CHOICES):
            output_func("Choose a number from the Export Reports menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Import / Export.")
            output_func("")
            return

        report_type = REPORT_EXPORT_CHOICE_TO_TYPE[choice]
        filters = _read_report_filters(report_type, input_func, output_func)
        if filters is None:
            output_func("Report export cancelled.")
            output_func("")
            continue

        try:
            result = service.export_report(report_type, **filters)
        except (
            ValidationError,
            RecordNotFoundError,
            DatabaseError,
            ExportFileError,
        ) as error:
            output_func(str(error))
            output_func("")
        else:
            _display_export_result(config, result, output_func)


def show_report_export_menu(output_func=print) -> None:
    """Display implemented report export types."""
    for line in format_title("EXPORT REPORTS"):
        output_func(line)

    for option in REPORT_EXPORT_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def show_recent_exports(
    service: ImportExportService,
    output_func=print,
) -> None:
    """Display recent files in the controlled export directory."""
    output_func("")
    for line in format_title("RECENT EXPORT FILES"):
        output_func(line)

    try:
        files = service.list_recent_exports()[1:]
    except ExportFileError as error:
        output_func(str(error))
        output_func("")
        return

    if not files:
        output_func("No export files found.")
        output_func("")
        return

    output_func(f"{'Filename':<46} {'Size':>10} Modified")
    output_func("-" * 78)
    for file_info in files:
        output_func(
            f"{file_info.filename:<46} "
            f"{file_info.size_bytes:>10} "
            f"{file_info.modified_at:%Y-%m-%d %H:%M:%S}"
        )
    output_func("")


def _run_import_flow(
    service: ImportExportService,
    import_type: str,
    input_func,
    output_func,
) -> None:
    label = IMPORT_LABELS[import_type]
    output_func("")
    output_func(f"{label} import uses CSV files staged in the import directory.")
    source_name = _prompt_required(
        "Enter CSV filename from import directory: ",
        input_func,
        output_func,
    )
    if source_name is None:
        output_func("Import cancelled.")
        output_func("")
        return

    preview = service.preview_import(import_type, source_name)
    _display_import_preview(preview, output_func)

    if not preview.is_importable:
        output_func("Import cannot proceed until errors are corrected.")
        output_func("")
        if not _confirm("Proceed? [y/N]: ", input_func, output_func):
            approved_preview = ImportPreview(
                import_type=preview.import_type,
                source_path=preview.source_path,
                total_rows=preview.total_rows,
                rows=preview.rows,
                warnings=preview.warnings,
            )
            if approved_preview.rows_to_create:
                service.commit_import(approved_preview)
        return

    if preview.rows_to_create == 0:
        output_func("No data rows were found. No data was imported.")
        output_func("")
        return

    if not _confirm("Proceed? [y/N]: ", input_func, output_func):
        output_func("Import cancelled. No data was imported.")
        output_func("")
        return

    try:
        result = service.commit_import(preview)
    except (
        ImportExportError,
        ValidationError,
        DuplicateRecordError,
        RecordNotFoundError,
        DatabaseError,
    ) as error:
        output_func("Import failed.")
        output_func("")
    else:
        output_func(f"Import completed: {result.created_count} record(s) created.")
        output_func("")


def _display_import_preview(
    preview: ImportPreview,
    output_func=print,
) -> None:
    label = IMPORT_LABELS.get(preview.import_type, preview.import_type)
    output_func("")
    for line in format_title(f"{label} Import Preview"):
        output_func(line)

    output_func(f"Selected file: {preview.source_path.name}")
    if preview.fatal_error is not None:
        output_func("")
        output_func("Import validation failed:")
        output_func(preview.fatal_error)
        return

    output_func("")
    output_func("Rows:")
    output_func(f"Total: {preview.total_rows}")
    output_func(f"Valid: {preview.valid_row_count}")
    output_func(f"Conflicts: {preview.conflict_count}")
    output_func(f"Invalid: {preview.invalid_row_count}")

    if preview.issues:
        output_func("")
        output_func("Import validation failed:")
        for issue in preview.issues:
            output_func(f"{issue.location}:")
            output_func(f"  {issue.field_name}: {issue.message}")
        return

    output_func("")
    output_func(f"Import will create {preview.rows_to_create} record(s).")


def _read_report_filters(
    report_type: str,
    input_func,
    output_func,
) -> dict[str, str | None] | None:
    if report_type == REPORT_SYSTEM_OVERVIEW:
        return {}
    if report_type == REPORT_STUDENT_PROGRESS:
        student_number = _prompt_required("Enter student number: ", input_func, output_func)
        if student_number is None:
            return None
        return {"student_number": student_number}
    if report_type == REPORT_COURSE_OVERVIEW:
        course_code = _prompt_required("Enter course code: ", input_func, output_func)
        if course_code is None:
            return None
        return {"course_code": course_code}
    if report_type == REPORT_ATTENDANCE:
        course_code = _prompt_required("Enter course code: ", input_func, output_func)
        if course_code is None:
            return None
        date_from = _prompt_optional("Date from [YYYY-MM-DD] (optional): ", input_func)
        if date_from == "q":
            return None
        date_to = _prompt_optional("Date to [YYYY-MM-DD] (optional): ", input_func)
        if date_to == "q":
            return None
        return {"course_code": course_code, "date_from": date_from, "date_to": date_to}
    if report_type == REPORT_LOW_ATTENDANCE:
        course_code = _prompt_required("Enter course code: ", input_func, output_func)
        if course_code is None:
            return None
        threshold = _prompt_optional(
            f"Threshold percentage [{DEFAULT_LOW_ATTENDANCE_THRESHOLD}]: ",
            input_func,
        )
        if threshold == "q":
            return None
        return {
            "course_code": course_code,
            "threshold_percentage": threshold or DEFAULT_LOW_ATTENDANCE_THRESHOLD,
        }
    if report_type == REPORT_ASSESSMENT_PERFORMANCE:
        assessment_id = _prompt_required("Enter assessment ID: ", input_func, output_func)
        if assessment_id is None:
            return None
        return {"assessment_id": assessment_id}
    if report_type == REPORT_TRAINER_ASSIGNMENT:
        trainer_number = _prompt_required(
            "Enter trainer number: ",
            input_func,
            output_func,
        )
        if trainer_number is None:
            return None
        return {"trainer_number": trainer_number}

    raise ValidationError(f"Unsupported report export type: {report_type}")


def _display_export_result(
    config: AppConfig,
    result: ExportResult,
    output_func=print,
) -> None:
    label = OPERATIONAL_EXPORT_LABELS.get(
        result.export_type,
        REPORT_EXPORT_LABELS.get(result.export_type, result.export_type),
    )
    output_func("")
    output_func(f"{label} export completed.")
    output_func(f"Format: {result.file_format.upper()}")
    output_func(f"Rows/lines: {result.row_count}")
    output_func(f"File: {_display_path(config, result.output_path)}")
    output_func("")


def _prompt_required(prompt: str, input_func, output_func) -> str | None:
    return prompt_required(prompt, input_func, output_func)


def _prompt_optional(prompt: str, input_func) -> str | None:
    return prompt_optional(prompt, input_func)


def _confirm(prompt: str, input_func, output_func) -> bool:
    return confirm(prompt, input_func, output_func)


def _read_text(prompt: str, input_func) -> str:
    return read_text(prompt, input_func)


def _is_cancel(value: str) -> bool:
    return is_cancel(value)


def _display_path(config: AppConfig, path) -> str:
    try:
        return str(path.relative_to(config.paths.project_root))
    except ValueError:
        return str(path)
