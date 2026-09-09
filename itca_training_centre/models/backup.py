"""Read models for controlled backup and restore workflows."""

from dataclasses import dataclass
from pathlib import Path


BACKUP_FORMAT_VERSION = 1
BACKUP_DIRECTORY_PREFIX = "backup_"
TEMP_BACKUP_DIRECTORY_PREFIX = ".tmp_backup_"
BACKUP_DATABASE_FILENAME = "database.sqlite3"
BACKUP_MANIFEST_FILENAME = "manifest.json"
BACKUP_CONFIG_FILENAME = "config.json"
BACKUP_REASON_MANUAL = "manual"
BACKUP_REASON_PRE_RESTORE = "pre_restore"


@dataclass(frozen=True)
class BackupRecordCount:
    """Row count for one table captured in a backup manifest."""

    table_name: str
    row_count: int


@dataclass(frozen=True)
class BackupManifest:
    """Versioned metadata stored with a managed backup package."""

    backup_format_version: int
    backup_id: str
    created_at: str
    application_name: str
    application_version: str
    migration_versions: tuple[int, ...]
    database_filename: str
    database_size_bytes: int
    database_sha256: str
    reason: str
    schema_version: int | None = None
    record_counts: tuple[BackupRecordCount, ...] = ()
    config_filename: str | None = None
    config_size_bytes: int | None = None
    config_sha256: str | None = None


@dataclass(frozen=True)
class BackupValidationResult:
    """Structured result of validating a backup package."""

    backup_id: str
    backup_path: Path
    valid: bool
    structure_valid: bool
    manifest_valid: bool
    checksum_valid: bool
    sqlite_integrity_valid: bool
    foreign_keys_valid: bool
    schema_compatible: bool
    issues: tuple[str, ...]
    created_at: str | None = None
    schema_version: int | None = None
    migration_versions: tuple[int, ...] = ()
    database_size_bytes: int | None = None
    database_sha256: str | None = None
    reason: str | None = None
    manifest: BackupManifest | None = None
    database_path: Path | None = None

    @property
    def message(self) -> str:
        """Return a concise human-readable validation summary."""
        if self.valid:
            return "Valid"
        if not self.issues:
            return "Invalid backup"
        return "; ".join(self.issues)


@dataclass(frozen=True)
class BackupInfo:
    """Compact read model for CLI backup listing and inspection."""

    backup_id: str
    created_at: str | None
    schema_version: int | None
    size_bytes: int | None
    sha256: str | None
    backup_path: Path
    database_path: Path | None
    manifest_path: Path | None
    reason: str | None
    is_valid: bool
    validation_message: str
    migration_versions: tuple[int, ...] = ()

    @property
    def short_sha256(self) -> str:
        """Return the abbreviated checksum used in CLI output."""
        if not self.sha256:
            return "unknown"
        return self.sha256[:8]


@dataclass(frozen=True)
class RestoreResult:
    """Result returned after a confirmed restore completes."""

    backup_id: str
    restored_schema_version: int
    safety_backup_id: str | None
    message: str
