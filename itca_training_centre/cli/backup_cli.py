"""Backup / Restore command-line screens."""

from dataclasses import dataclass

from ..config.settings import AppConfig
from ..models.backup import BackupInfo, BackupValidationResult
from ..services.backup_service import BackupService
from ..utils.exceptions import (
    BackupError,
    BackupValidationError,
    RecordNotFoundError,
    RestoreError,
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


@dataclass(frozen=True)
class BackupRestoreMenuOption:
    """A numbered Backup / Restore menu option."""

    choice: str
    label: str


BACKUP_RESTORE_MENU_OPTIONS = (
    BackupRestoreMenuOption("1", "Create Backup"),
    BackupRestoreMenuOption("2", "List Backups"),
    BackupRestoreMenuOption("3", "Inspect / Validate Backup"),
    BackupRestoreMenuOption("4", "Restore Backup"),
    BackupRestoreMenuOption("0", "Back"),
)

VALID_BACKUP_RESTORE_MENU_CHOICES = tuple(
    option.choice for option in BACKUP_RESTORE_MENU_OPTIONS
)


def run_backup_restore_menu(
    config: AppConfig,
    input_func=input,
    output_func=print,
    service: BackupService | None = None,
) -> None:
    """Run the Backup / Restore submenu."""
    workflows = service or BackupService.from_config(config)

    while True:
        show_backup_restore_menu(output_func=output_func)
        choice = read_menu_choice("Select an option: ", input_func=input_func)

        if not is_valid_menu_choice(choice, VALID_BACKUP_RESTORE_MENU_CHOICES):
        output_func("Choose a number from the Backup / Restore menu.")
            output_func("")
            continue

        if choice == "0":
            output_func("Returning to Main Menu.")
            output_func("")
            return
        if choice == "1":
            create_backup(config, workflows, input_func, output_func)
        elif choice == "2":
            list_backups(workflows, output_func)
        elif choice == "3":
            inspect_backup(workflows, input_func, output_func)
        elif choice == "4":
            restore_backup(workflows, input_func, output_func)


def show_backup_restore_menu(output_func=print) -> None:
    """Display the Backup / Restore menu."""
    for line in format_title("BACKUP / RESTORE"):
        output_func(line)

    for option in BACKUP_RESTORE_MENU_OPTIONS:
        output_func(f"{option.choice}. {option.label}")


def create_backup(
    config: AppConfig,
    service: BackupService,
    input_func=input,
    output_func=print,
) -> None:
    """Create a backup after collecting an optional metadata note."""
    output_func("")
    for line in format_title("CREATE BACKUP"):
        output_func(line)

    note = _prompt_optional("Optional note [manual]: ", input_func)
    if note == "q":
        output_func("Backup cancelled.")
        output_func("")
        return

    output_func("Creating backup...")
    try:
        backup = service.create_backup(reason=note or "manual")
    except (BackupError, ValidationError) as error:
        output_func(str(error))
        output_func("")
        return

    output_func("Backup created successfully.")
    _display_backup_info(config, backup, output_func)


def list_backups(
    service: BackupService,
    output_func=print,
) -> tuple[BackupInfo, ...]:
    """Display managed backups."""
    output_func("")
    for line in format_title("BACKUPS"):
        output_func(line)

    try:
        backups = service.list_backups()
    except BackupError as error:
        output_func(str(error))
        output_func("")
        return ()

    if not backups:
        output_func("No backups found.")
        output_func("")
        return ()

    output_func(f"{'ID':<27} {'Created':<22} {'Schema':<6} {'Size':>12} Status")
    output_func("-" * 78)
    for backup in backups:
        output_func(
            f"{backup.backup_id:<27} "
            f"{_display_value(backup.created_at):<22} "
            f"{_display_value(backup.schema_version):<6} "
            f"{_format_size(backup.size_bytes):>12} "
            f"{'Valid' if backup.is_valid else 'Invalid'}"
        )
    output_func("")
    return backups


def inspect_backup(
    service: BackupService,
    input_func=input,
    output_func=print,
) -> None:
    """Display one backup and its validation details."""
    backup_id = _prompt_required("Enter backup ID: ", input_func, output_func)
    if backup_id is None:
        output_func("Backup inspection cancelled.")
        output_func("")
        return

    try:
        backup = service.inspect_backup(backup_id)
        validation = service.validate_backup(backup_id)
    except (BackupError, RecordNotFoundError, ValidationError) as error:
        output_func(str(error))
        output_func("")
        return

    _display_backup_info(None, backup, output_func)
    _display_validation_result(validation, output_func)


def restore_backup(
    service: BackupService,
    input_func=input,
    output_func=print,
) -> None:
    """Validate and restore a selected managed backup after confirmation."""
    backups = list_backups(service, output_func)
    if not backups:
        return

    backup_id = _prompt_required("Enter backup ID to restore: ", input_func, output_func)
    if backup_id is None:
        output_func("Restore cancelled.")
        output_func("")
        return

    try:
        validation = service.validate_backup(backup_id)
    except (BackupError, RecordNotFoundError, ValidationError) as error:
        output_func(str(error))
        output_func("")
        return

    output_func("")
    for line in format_title("RESTORE DATABASE"):
        output_func(line)
    _display_restore_summary(validation, output_func)

    if not validation.valid:
        output_func("Backup is invalid and cannot be restored.")
        output_func("")
        return

    output_func("Restoring this backup will replace the current application database.")
    output_func("A safety backup of the current database will be created first.")
    if _confirm("Proceed? [y/N]: ", input_func, output_func):
        output_func("Restore cancelled. Live database was not changed.")
        output_func("")
        return

    try:
        result = service.restore_backup(backup_id)
    except (
        BackupError,
        BackupValidationError,
        RecordNotFoundError,
        RestoreError,
        ValidationError,
    ) as error:
        output_func(str(error))
        output_func("")
        return

    output_func(result.message)
    if result.safety_backup_id is not None:
        output_func(f"Safety backup ID: {result.safety_backup_id}")
    output_func(f"Schema version: {result.restored_schema_version}")
    output_func("")


def _display_backup_info(
    config: AppConfig | None,
    backup: BackupInfo,
    output_func=print,
) -> None:
    output_func("")
    output_func(f"Backup ID: {backup.backup_id}")
    output_func(f"Created: {_display_value(backup.created_at)}")
    output_func(f"Schema Version: {_display_value(backup.schema_version)}")
    output_func(f"Migration History: {_format_versions(backup.migration_versions)}")
    output_func(f"Size: {_format_size(backup.size_bytes)}")
    output_func(f"Checksum: {backup.short_sha256}")
    output_func(f"Reason: {_display_value(backup.reason)}")
    output_func(f"Status: {'Valid' if backup.is_valid else 'Invalid'}")
    if not backup.is_valid:
        output_func(f"Validation: {backup.validation_message}")
    elif config is not None:
        output_func(f"Location: {_display_path(config, backup.backup_path)}")
    output_func("")


def _display_validation_result(
    validation: BackupValidationResult,
    output_func=print,
) -> None:
    output_func("Validation")
    output_func(f"{'Manifest':<24} {_status(validation.manifest_valid)}")
    output_func(f"{'Checksum':<24} {_status(validation.checksum_valid)}")
    output_func(f"{'SQLite integrity':<24} {_status(validation.sqlite_integrity_valid)}")
    output_func(f"{'Foreign keys':<24} {_status(validation.foreign_keys_valid)}")
    output_func(f"{'Schema compatibility':<24} {_status(validation.schema_compatible)}")
    output_func(f"Overall: {'VALID' if validation.valid else 'INVALID'}")
    for issue in validation.issues:
        output_func(f"- {issue}")
    output_func("")


def _display_restore_summary(
    validation: BackupValidationResult,
    output_func=print,
) -> None:
    output_func(f"Backup ID: {validation.backup_id}")
    output_func(f"Created: {_display_value(validation.created_at)}")
    output_func(f"Schema Version: {_display_value(validation.schema_version)}")
    output_func(f"Status: {'Valid' if validation.valid else 'Invalid'}")
    output_func(f"Checksum: {_display_value(validation.database_sha256)[:12]}")
    if validation.issues:
        for issue in validation.issues:
            output_func(f"- {issue}")
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


def _display_value(value) -> str:
    if value is None:
        return "unknown"
    return str(value)


def _format_versions(versions: tuple[int, ...]) -> str:
    if not versions:
        return "none"
    return ", ".join(str(version) for version in versions)


def _format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unknown"
    return f"{size_bytes} bytes"


def _status(value: bool) -> str:
    return value


def _display_path(config: AppConfig, path) -> str:
    try:
        return str(path.relative_to(config.paths.project_root))
    except ValueError:
        return str(path)
