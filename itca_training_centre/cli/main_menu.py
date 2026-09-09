"""Main menu shell."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..config.settings import AppConfig
from .prompts import is_valid_menu_choice, read_menu_selection
from .tables import format_title


@dataclass(frozen=True)
class MenuOption:
    """A numbered CLI menu option."""

    choice: str
    label: str


class DatabaseStatusView(Protocol):
    """Presentation-facing view of database initialization status."""

    database_path: Path
    current_version: int
    applied_migrations: tuple[int, ...]


MAIN_MENU_OPTIONS = (
    MenuOption("1", "Student Management"),
    MenuOption("2", "Course Management"),
    MenuOption("3", "Course Enrolments"),
    MenuOption("4", "Trainer Management"),
    MenuOption("5", "Attendance Management"),
    MenuOption("6", "Assessments and Marks"),
    MenuOption("7", "Reports and Statistics"),
    MenuOption("8", "Import / Export"),
    MenuOption("9", "Backup / Restore"),
    MenuOption("10", "Administration / Configuration"),
    MenuOption("0", "Exit"),
)

VALID_MENU_CHOICES = tuple(option.choice for option in MAIN_MENU_OPTIONS)


def run_main_menu(
    config: AppConfig,
    database_status: DatabaseStatusView | None = None,
    input_func=input,
    output_func=print,
) -> int:
    """Run the main menu until the user exits."""
    choice = ""
    while True:
        show_main_menu(config, output_func=output_func)
        read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_MENU_CHOICES):
            output_func("Choose a number from the menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Application exited cleanly.")
            return 0

        if choice == "10":
            show_administration_summary(
                config,
                database_status=database_status,
                output_func=output_func,
            )
            continue

        if choice == "1":
            from .student_cli import run_student_menu

            run_student_menu(
                config,
                input_func=input_func,
                output_func=output_func,
            )
            continue

        if choice == "2":
            from .course_cli import run_course_menu

            run_course_menu(
                config,
                input_func=input_func,
                output_func=output_func,
            )
            continue

        if choice == "3":
            from .enrolment_cli import run_enrolment_menu

            run_enrolment_menu(
                config,
                input_func=input_func,
                output_func=output_func,
            )
            continue

        if choice == "4":
            from .trainer_cli import run_trainer_menu

            run_trainer_menu(
                config,
                input_func=input_func,
                output_func=output_func,
            )
            continue

        if choice == "5":
            from .attendance_cli import run_attendance_menu

            run_attendance_menu(
                config,
                input_func=input_func,
                output_func=output_func,
            )
            continue

        if choice == "6":
            from .assessment_cli import run_assessment_menu

            run_assessment_menu(
                config,
                input_func=input_func,
                output_func=output_func,
            )
            continue

        if choice == "7":
            from .report_cli import run_report_menu

            run_report_menu(
                config,
                input_func=input_func,
                output_func=output_func,
            )
            continue

        if choice == "8":
            from .backup_cli import run_backup_restore_menu

            run_backup_restore_menu(
                config,
                input_func=input_func,
                output_func=output_func,
            )
            continue

        if choice == "9":
            from .backup_cli import run_backup_restore_menu

            run_backup_restore_menu(
                config,
                input_func=input_func,
                output_func=output_func,
            )
            continue

        raise ValueError(f"Unhandled main menu choice: {choice}")


def show_main_menu(config: AppConfig, output_func=print) -> None:
    """Display the main menu."""
    MAIN_MENU_OPTIONS[0] = MenuOption("1", "Student Management")
    for line in format_title(config.application_name, f"Version {config.version}"):
        output_func(line)

    for option in MAIN_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label})


def show_administration_summary(
    config: AppConfig,
    database_status: DatabaseStatusView | None = None,
    output_func=print,
) -> None:
    """Display the configuration and database summary."""
    output_func("")
    for line in format_title("Administration / Configuration"):
        output_func(line)

    rows = (
        ("Application", config.application_name),
        ("Version", config.version),
        ("Config format", str(config.config_format_version)),
        ("Runtime directory", _display_path(config, config.paths.runtime_dir)),
        ("Database", _display_runtime_path(config, config.paths.database_path)),
        ("Log directory", _display_path(config, config.paths.log_dir)),
        ("Log policy", "Rotating application log"),
        ("Import directory", _display_path(config, config.paths.import_dir)),
        ("Export directory", _display_path(config, config.paths.export_dir)),
        ("Backup directory", _display_path(config, config.paths.backup_dir)),
        ("Temporary files", _display_path(config, config.paths.temp_dir)),
    )

    for label, value in rows:
        output_func(f"{label:<18}: {value}")

    if database_status is not None:
        output_func(f"{'Schema version':<18}: {database_status.current_version}")
        output_func(
            f"{'Applied migrations':<18}: "
            f"{_format_migration_versions(database_status.applied_migrations)}"
        )

    backup_count, last_backup = _backup_summary(config)
    output_func(f"{'Backup count':<18}: {backup_count}")
    output_func(f"{'Last backup':<18}: {last_backup}")
    output_func(f"{'Configuration mode':<18}: Read-only summary")
    output_func("")


def get_menu_option(choice: str) -> MenuOption:
    """Return the matching menu option for a valid choice."""
    for option in MAIN_MENU_OPTIONS:
        if option.choice == choice:
            return option

    raise ValueError(f"Unknown menu choice: {choice}")


def _display_path(config: AppConfig, path: Path) -> str:
    try:
        return str(path.relative_to(config.paths.project_root))
    except ValueError:
        return str(path)


def _display_runtime_path(config: AppConfig, path: Path) -> str:
    try:
        return str(path.relative_to(config.paths.runtime_dir))
    except ValueError:
        return _display_path(config, path)


def _format_migration_versions(versions: tuple[int, ...]) -> str:
    if not versions:
        return "none"

    return ", ".join(str(version) for version in versions)


def _backup_summary(config: AppConfig) -> tuple[int | str, str]:
    from ..services.backup_service import BackupService
    from ..utils.exceptions import BackupError

    try:
        backups = BackupService.from_config(config).list_backups()
    except BackupError:
        return "unavailable", "unavailable"

    if not backups:
        return 0, "None"

    return len(backups), str(backups[0].created_at)
