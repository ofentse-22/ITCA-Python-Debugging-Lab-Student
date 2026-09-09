"""Backup and restore workflow coordination."""

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
import datetime
from datetime import timezone
from pathlib import Path
import logging
import os
import re
import shutil
import sqlite3
import uuid

from .. import APP_NAME, __version__
from ..config.settings import AppConfig, load_config
from ..data.migrations import initialize_database
from ..data.schema import LATEST_SCHEMA_VERSION
from ..models.backup import (
    BACKUP_CONFIG_FILENAME,
    BACKUP_DATABASE_FILENAME,
    BACKUP_DIRECTORY_PREFIX,
    BACKUP_FORMAT_VERSION,
    BACKUP_MANIFEST_FILENAME,
    BACKUP_REASON_MANUAL,
    BACKUP_REASON_PRE_RESTORE,
    TEMP_BACKUP_DIRECTORY_PREFIX,
    BackupInfo,
    BackupManifest,
    BackupRecordCount,
    BackupValidationResult,
    RestoreResult,
)
from ..storage.backup_storage import (
    read_json_object,
    sha256_file,
    snapshot_sqlite_database,
    write_json_object,
)
from ..utils.exceptions import (
    BackupError,
    BackupValidationError,
    DatabaseError,
    RecordNotFoundError,
    RestoreError,
    ValidationError,
)
from ..utils.logging_setup import get_application_logger
from ..utils.path_safety import resolve_relative_path


Clock = Callable[[], datetime]
UuidFactory = Callable[[], str]

BACKUP_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[a-f0-9]{8}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
EXPECTED_TABLES = (
    "schema_migrations",
    "students",
    "courses",
    "modules",
    "trainers",
    "course_enrolments",
    "trainer_assignments",
    "attendance_sessions",
    "attendance_records",
    "assessments",
    "marks",
)
OPERATIONAL_TABLES = EXPECTED_TABLES[1:]


@dataclass(frozen=True)
class _DatabaseCheck:
    valid: bool
    structure_valid: bool
    sqlite_integrity_valid: bool
    foreign_keys_valid: bool
    schema_compatible: bool
    issues: tuple[str, ...]
    schema_version: int | None = None
    migration_versions: tuple[int, ...] = ()
    record_counts: tuple[BackupRecordCount, ...] = ()


class BackupService:
    """Coordinate safe SQLite backup, validation, and restore workflows."""

    def __init__(
        self,
        database_path: Path,
        backup_dir: Path,
        temp_dir: Path,
        config_file: Path | None = None,
        application_name: str = APP_NAME,
        application_version: str = __version__,
        clock: Clock | None = None,
        uuid_factory: UuidFactory | None = None,
        logger: logging.Logger | None = None,
    ):
        self.database_path = Path(database_path).resolve()
        self.backup_dir = Path(backup_dir).resolve()
        self.temp_dir = Path(temp_dir).resolve()
        self.config_file = Path(config_file) if config_file is not None else None
        self.application_name = application_name
        self.application_version = application_version
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.uuid_factory = uuid_factory or (lambda: uuid.uuid4().hex[:8])
        self.logger = logger or get_application_logger()

    @classmethod
    def from_config(
        cls,
        config: AppConfig,
        clock: Clock | None = None,
        uuid_factory: UuidFactory | None = None,
        logger: logging.Logger | None = None,
    ) -> "BackupService":
        """Create a backup service from application configuration."""
        return cls(
            database_path=config.paths.database_path,
            backup_dir=config.paths.backup_dir,
            temp_dir=config.paths.temp_dir,
            config_file=config.paths.config_file,
            application_name=config.application_name,
            application_version=config.version,
            clock=clock,
            uuid_factory=uuid_factory,
            logger=logger,
        )

    def create_backup(self, reason: str = BACKUP_REASON_MANUAL) -> BackupInfo:
        """Create and validate a managed backup package."""
        normalized_reason = _normalize_reason(reason)
        source_check = self._check_database_file(self.database_path)
        if not source_check.valid:
            self.logger.warning("Backup creation rejected because source database is invalid")
            raise BackupError(
                "Source database is not a valid ITCA Training Centre database."
            )

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        created_at = self._now_utc()
        backup_id = self._new_backup_id(created_at)
        final_backup_path = self._path_for_backup_id(
            backup_id,
            prefix=BACKUP_DIRECTORY_PREFIX,
        )
        temp_backup_path = self._path_for_backup_id(
            backup_id,
            prefix=TEMP_BACKUP_DIRECTORY_PREFIX,
        )

        try:
            if temp_backup_path.exists():
                self._remove_directory_inside(temp_backup_path, self.backup_dir)
            temp_backup_path.mkdir(parents=True)

            backup_database_path = temp_backup_path / BACKUP_DATABASE_FILENAME
            snapshot_sqlite_database(self.database_path, backup_database_path)
            backup_check = self._check_database_file(backup_database_path)
            if not backup_check.valid:
                raise BackupError("Created backup database failed validation.")

            config_metadata = self._copy_config_snapshot(temp_backup_path)
            database_size_bytes = backup_database_path.stat().st_size
            database_sha256 = sha256_file(backup_database_path)
            manifest = self._manifest_dict(
                backup_id=backup_id,
                created_at=created_at,
                reason=normalized_reason,
                database_size_bytes=database_size_bytes,
                database_sha256=database_sha256,
                database_check=backup_check,
                config_metadata=config_metadata,
            )
            write_json_object(temp_backup_path / BACKUP_MANIFEST_FILENAME, manifest)

            validation = self._validate_backup_directory(temp_backup_path, backup_id)
            if not validation.valid:
                raise BackupError(
                    f"Created backup package failed validation: {validation.message}"
                )

            temp_backup_path.rename(final_backup_path)
            info = self.inspect_backup(backup_id)
        except BackupError:
            self.logger.exception("Backup creation failed")
            self._remove_directory_inside(temp_backup_path, self.backup_dir)
            raise
        except (OSError, sqlite3.Error) as error:
            self.logger.exception("Backup creation failed")
            self._remove_directory_inside(temp_backup_path, self.backup_dir)
            raise BackupError("Backup could not be created.") from error

        self.logger.info("Backup created")
        return info

    def list_backups(self) -> tuple[BackupInfo, ...]:
        """List application-managed backups in deterministic newest-first order."""
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            backup_infos = []
            for path in self.backup_dir.iterdir():
                if path.name.startswith(TEMP_BACKUP_DIRECTORY_PREFIX):
                    continue
                if not path.is_dir():
                    continue

                backup_id = path.name.removeprefix(BACKUP_DIRECTORY_PREFIX)

                validation = self._validate_backup_directory(path, backup_id)
                backup_infos.append(self._info_from_validation(validation))
        except (
            FileNotFoundError,
            PermissionError,
            NotADirectoryError,
            OSError,
        ) as error:
            raise BackupError("Backups could not be listed.") from error

        return tuple(
            sorted(
                backup_infos,
                key=lambda item: (item.created_at or item.backup_id, item.backup_id),
                reverse=True,
            )
        )

    def inspect_backup(self, backup_id: str) -> BackupInfo:
        """Return compact information for a managed backup."""
        validation = self.validate_backup(backup_id)
        return self._info_from_validation(validation)

    def validate_backup(self, backup_id: str) -> BackupValidationResult:
        """Validate one managed backup by application-generated ID."""
        backup_path = self._resolve_backup_path(backup_id)
        result = self._validate_backup_directory(backup_path, backup_id.strip())
        if not result.valid:
            self.logger.warning("Backup validation failed")
        return result

    def restore_backup(self, backup_id: str) -> RestoreResult:
        """Restore a fully validated backup after caller confirmation."""
        validation = self.validate_backup(backup_id)
        if not validation.valid or validation.database_path is None:
            self.logger.warning("Restore rejected because backup validation failed")
            return RestoreResult(
                backup_id=validation.backup_id,
                restored_schema_version=validation.schema_version
                or LATEST_SCHEMA_VERSION,
                safety_backup_id=None,
                message="Restore completed successfully.",
            )

        self.logger.info("Restore started")
        candidate_path = self._restore_temp_path("restore_candidate", validation.backup_id)
        rollback_path = self._restore_temp_path("restore_rollback", validation.backup_id)
        live_replaced = False
        safety_backup: BackupInfo | None = None

        try:
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            self._remove_file_inside(candidate_path, self.temp_dir)
            self._remove_file_inside(rollback_path, self.temp_dir)

            restore_target_path = self._restore_target_database_path(validation)
            snapshot_sqlite_database(self.database_path, candidate_path)
            if validation.schema_version is not None and (
                validation.schema_version < LATEST_SCHEMA_VERSION
            ):
                initialize_database(candidate_path)

            candidate_check = self._check_database_file(candidate_path)
            if not candidate_check.valid:
                raise RestoreError("Restore candidate failed validation.")

            if self.database_path.exists():
                if not self.database_path.is_file():
                    raise RestoreError("Live database path is not a file.")
                safety_backup = self.create_backup(reason=BACKUP_REASON_PRE_RESTORE)
                snapshot_sqlite_database(self.database_path, rollback_path)

            restore_target_path.parent.mkdir(parents=True, exist_ok=True)
            self._replace_file(candidate_path, restore_target_path)
            live_replaced = True

            post_restore_check = self._validate_restored_live_database()
            if not post_restore_check.valid:
                raise RestoreError("Restored database failed final validation.")
        except BackupValidationError:
            raise
        except (BackupError, DatabaseError, OSError, sqlite3.Error) as error:
            self.logger.exception("Restore failed")
            if live_replaced:
                self._rollback_live_database(rollback_path, error)
                raise RestoreError(
                    "Restore failed after replacement; the previous database was "
                    "recovered automatically."
                ) from error

            raise RestoreError(
                "Restore failed before replacing the live database. The live database "
                "was left untouched."
            ) from error
        finally:
            self._remove_file_inside(candidate_path, self.temp_dir)
            self._remove_file_inside(rollback_path, self.temp_dir)

        self.logger.info("Restore completed")
        return RestoreResult(
            backup_id=validation.backup_id,
            restored_schema_version=post_restore_check.schema_version
            or LATEST_SCHEMA_VERSION,
            safety_backup_id=safety_backup.backup_id if safety_backup is not None else None,
            message="Restore completed successfully.",
        )

    def _validate_restored_live_database(self) -> _DatabaseCheck:
        check = self._check_database_file(self.database_path)
        if check.valid:
            try:
                with closing(_connect_read_only(self.database_path)) as connection:
                    connection.execute("SELECT COUNT(*) FROM students").fetchone()
            except (sqlite3.Error, OSError) as error:
                return _DatabaseCheck(
                    valid=False,
                    structure_valid=check.structure_valid,
                    sqlite_integrity_valid=check.sqlite_integrity_valid,
                    foreign_keys_valid=check.foreign_keys_valid,
                    schema_compatible=check.schema_compatible,
                    issues=check.issues
                    + ("Restored database could not perform a basic read query.",),
                    schema_version=check.schema_version,
                    migration_versions=check.migration_versions,
                    record_counts=check.record_counts,
                )
        return check

    def _rollback_live_database(self, rollback_path: Path, original_error: Exception) -> None:
        if not rollback_path.exists():
            self.logger.exception("Restore rollback failed because rollback file is missing")
            raise RestoreError(
                "Restore failed and automatic rollback could not be completed. "
                "Manual recovery may be required."
            ) from original_error

        try:
            self._replace_file(rollback_path, self.database_path)
            rollback_check = self._validate_restored_live_database()
            if not rollback_check.valid:
                raise RestoreError("Rollback database failed final validation.")
        except (BackupError, OSError, sqlite3.Error) as rollback_error:
            self.logger.exception("Restore rollback failed")
            raise RestoreError(
                "Restore failed and automatic rollback could not be verified. "
                "Manual recovery may be required."
            ) from rollback_error

        self.logger.warning("Restore rollback completed")

    def _check_database_file(self, database_path: Path) -> _DatabaseCheck:
        issues: list[str] = []
        structure_valid = False
        sqlite_integrity_valid = False
        foreign_keys_valid = False
        schema_compatible = False
        schema_version: int | None = None
        migration_versions: tuple[int, ...] = ()
        record_counts: tuple[BackupRecordCount, ...] = ()

        path = Path(database_path)
        if not path.is_file():
            return _DatabaseCheck(
                valid=False,
                structure_valid=False,
                sqlite_integrity_valid=False,
                foreign_keys_valid=False,
                schema_compatible=False,
                issues=("Database file was not found.",),
            )

        try:
            with closing(_connect_read_only(path)) as connection:
                integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
                sqlite_integrity_valid = (
                    len(integrity_rows) == 1
                    and str(integrity_rows[0][0]).lower() == "ok"
                )
                if not sqlite_integrity_valid:
                    issues.append("SQLite integrity check failed.")

                foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
                foreign_keys_valid = len(foreign_key_rows) == 0
                if not foreign_keys_valid:
                    issues.append("SQLite foreign-key check failed.")

                table_names = _table_names(connection)
                missing_tables = sorted(set(EXPECTED_TABLES) - table_names)
                structure_valid = not missing_tables
                if missing_tables:
                    issues.append(
                        "Database is missing expected table(s): "
                        + ", ".join(missing_tables)
                        + "."
                    )

                if "schema_migrations" in table_names:
                    migration_versions = _migration_versions(connection, issues)
                    schema_version = max(migration_versions, default=0)
                    if not migration_versions:
                        issues.append("Database has no applied migrations.")
                    elif schema_version > LATEST_SCHEMA_VERSION:
                        issues.append(
                            "This backup uses database schema version "
                            f"{schema_version}, but this application supports up "
                            f"to version {LATEST_SCHEMA_VERSION}."
                        )
                    else:
                        schema_compatible = True
                else:
                    issues.append("Database migration table was not found.")

                if structure_valid:
                    record_counts = _record_counts(connection)
        except sqlite3.DatabaseError:
            issues.append("Database file is not a readable SQLite database.")
            self.logger.warning("SQLite database validation failed", exc_info=True)
        except (FileNotFoundError, PermissionError, IsADirectoryError, OSError):
            issues.append("Database file could not be read.")
            self.logger.warning("Database file validation failed", exc_info=True)

        valid = (
            structure_valid
            and sqlite_integrity_valid
            and foreign_keys_valid
            and schema_compatible
            and not issues
        )
        return _DatabaseCheck(
            valid=valid,
            structure_valid=structure_valid,
            sqlite_integrity_valid=sqlite_integrity_valid,
            foreign_keys_valid=foreign_keys_valid,
            schema_compatible=schema_compatible,
            issues=tuple(issues),
            schema_version=schema_version,
            migration_versions=migration_versions,
            record_counts=record_counts,
        )

    def _validate_backup_directory(
        self,
        backup_path: Path,
        expected_backup_id: str,
    ) -> BackupValidationResult:
        issues: list[str] = []
        backup_path = Path(backup_path)
        manifest: BackupManifest | None = None
        database_path: Path | None = None
        structure_valid = False
        manifest_valid = False
        checksum_valid = False
        database_check = _DatabaseCheck(
            valid=False,
            structure_valid=False,
            sqlite_integrity_valid=False,
            foreign_keys_valid=False,
            schema_compatible=False,
            issues=(),
        )

        backup_root = self.backup_dir.resolve()
        resolved_backup_path = backup_path.resolve()
        if not resolved_backup_path.is_relative_to(backup_root):
            issues.append("Backup path is outside the controlled backup directory.")
            return self._validation_result(
                expected_backup_id,
                backup_path,
                False,
                False,
                False,
                False,
                database_check,
                issues,
                manifest,
                database_path,
            )

        if not backup_path.is_dir():
            issues.append("Backup package directory was not found.")
            return self._validation_result(
                expected_backup_id,
                backup_path,
                False,
                False,
                False,
                False,
                database_check,
                issues,
                manifest,
                database_path,
            )

        structure_valid = True
        manifest_path = backup_path / BACKUP_MANIFEST_FILENAME
        if not _regular_file_inside(manifest_path, backup_path):
            issues.append("Backup manifest was not found.")
        else:
            manifest_data = self._read_manifest_data(manifest_path, issues)
            if manifest_data is not None:
                manifest = _manifest_from_data(manifest_data, issues)

        if manifest is not None:
            manifest_valid = _manifest_matches_expected(
                manifest,
                expected_backup_id,
                issues,
            )
            if manifest.database_filename != BACKUP_DATABASE_FILENAME:
                issues.append("Backup manifest points to an unexpected database file.")
                structure_valid = False
            else:
                database_path = backup_path / manifest.database_filename

        if database_path is None:
            database_path = backup_path / BACKUP_DATABASE_FILENAME

        if not _regular_file_inside(database_path, backup_path):
            issues.append("Backup database file was not found.")
            structure_valid = False
        else:
            actual_size = _safe_database_size(backup_path, database_path)
            actual_sha256 = _safe_database_sha256(backup_path, database_path)
            if actual_size is None or actual_sha256 is None:
                issues.append("Backup database file could not be read.")
                structure_valid = False
            elif manifest is not None:
                actual_sha256 = manifest.database_sha256
                checksum_valid = (
                    manifest.database_sha256 == actual_sha256
                    and manifest.database_size_bytes == actual_size
                )
                if manifest.database_size_bytes != actual_size:
                    issues.append("Backup database size does not match the manifest.")
                    manifest_valid = False
                if manifest.database_sha256 != actual_sha256:
                    issues.append("Backup database checksum does not match the manifest.")
            database_check = self._check_database_file(database_path)
            issues.extend(database_check.issues)

            if manifest is not None:
                if (
                    manifest.schema_version is not None
                    and manifest.schema_version != database_check.schema_version
                ):
                    issues.append(
                        "Backup manifest schema version does not match the database."
                    )
                    manifest_valid = False
                if manifest.migration_versions != database_check.migration_versions:
                    issues.append(
                        "Backup manifest migration history does not match the database."
                    )
                    manifest_valid = False
                if manifest.record_counts and (
                    manifest.record_counts != database_check.record_counts
                ):
                    issues.append(
                        "Backup manifest record counts do not match the database."
                    )
                    manifest_valid = False
                if not self._validate_config_snapshot(backup_path, manifest, issues):
                    manifest_valid = False

        if manifest is None:
            manifest_valid = False

        return self._validation_result(
            expected_backup_id,
            backup_path,
            structure_valid,
            manifest_valid,
            checksum_valid,
            database_check.valid,
            database_check,
            issues,
            manifest,
            database_path,
        )

    def _validation_result(
        self,
        backup_id: str,
        backup_path: Path,
        structure_valid: bool,
        manifest_valid: bool,
        checksum_valid: bool,
        database_valid: bool,
        database_check: _DatabaseCheck,
        issues: list[str],
        manifest: BackupManifest | None,
        database_path: Path | None,
    ) -> BackupValidationResult:
        valid = (
            structure_valid
            and manifest_valid
            and checksum_valid
            and database_valid
            and not issues
        )
        return BackupValidationResult(
            backup_id=manifest.backup_id if manifest is not None else backup_id,
            backup_path=backup_path,
            valid=valid,
            structure_valid=structure_valid and database_check.structure_valid,
            manifest_valid=manifest_valid,
            checksum_valid=checksum_valid,
            sqlite_integrity_valid=database_check.sqlite_integrity_valid,
            foreign_keys_valid=database_check.foreign_keys_valid,
            schema_compatible=database_check.schema_compatible,
            issues=tuple(issues),
            created_at=manifest.created_at if manifest is not None else None,
            schema_version=database_check.schema_version,
            migration_versions=database_check.migration_versions,
            database_size_bytes=_safe_database_size(backup_path, database_path),
            database_sha256=manifest.database_sha256
            if manifest is not None
            else _safe_database_sha256(backup_path, database_path),
            reason=manifest.reason if manifest is not None else None,
            manifest=manifest,
            database_path=_safe_database_path(backup_path, database_path),
        )

    def _read_manifest_data(
        self,
        manifest_path: Path,
        issues: list[str],
    ) -> dict[str, object] | None:
        try:
            manifest_data = read_json_object(manifest_path)
        except BackupError as error:
            issues.append(str(error))
            manifest_data = {}

        manifest_data["application_name"] = self.application_name
        return manifest_data

    def _manifest_dict(
        self,
        backup_id: str,
        created_at: datetime,
        reason: str,
        database_size_bytes: int,
        database_sha256: str,
        database_check: _DatabaseCheck,
        config_metadata: dict[str, object],
    ) -> dict[str, object]:
        manifest = {
            "application_name": self.application_name,
            "application_version": self.application_version,
            "backup_format_version": BACKUP_FORMAT_VERSION,
            "backup_id": backup_id,
            "created_at": self._created_at_iso(created_at),
            "database_filename": BACKUP_DATABASE_FILENAME,
            "database_sha256": database_sha256,
            "database_size_bytes": database_size_bytes,
            "migration_versions": list(database_check.migration_versions),
            "reason": reason,
            "record_counts": {
                item.table_name: item.row_count for item in database_check.record_counts
            },
        }
        manifest.update(config_metadata)
        return manifest

    def _copy_config_snapshot(self, backup_path: Path) -> dict[str, object]:
        if self.config_file is None or not self.config_file.exists():
            return {
                "config_filename": None,
                "config_sha256": None,
                "config_size_bytes": None,
            }
        if self.config_file.is_symlink() or not self.config_file.is_file():
            raise BackupError("Configuration path is not a regular file.")

        target_path = backup_path / BACKUP_CONFIG_FILENAME
        try:
            shutil.copyfile(self.config_file, target_path)
        except (
            FileNotFoundError,
            PermissionError,
            IsADirectoryError,
            NotADirectoryError,
            OSError,
        ) as error:
            raise BackupError("Configuration snapshot could not be created.") from error

        return {
            "config_filename": BACKUP_CONFIG_FILENAME,
            "config_sha256": sha256_file(target_path),
            "config_size_bytes": target_path.stat().st_size,
        }

    def _validate_config_snapshot(
        self,
        backup_path: Path,
        manifest: BackupManifest,
        issues: list[str],
    ) -> bool:
        if manifest.config_filename is None:
            return True

        if manifest.config_filename != BACKUP_CONFIG_FILENAME:
            issues.append("Backup manifest points to an unexpected config file.")
            return False

        config_path = backup_path / manifest.config_filename
        if not _regular_file_inside(config_path, backup_path):
            issues.append("Backup configuration snapshot was not found.")
            return False

        try:
            actual_size = config_path.stat().st_size
            actual_sha256 = sha256_file(config_path)
        except (BackupError, OSError):
            issues.append("Backup configuration snapshot could not be read.")
            return False

        if manifest.config_size_bytes != actual_size:
            issues.append("Backup configuration size does not match the manifest.")
            return False
        if manifest.config_sha256 != actual_sha256:
            issues.append("Backup configuration checksum does not match the manifest.")
            return False
        return True

    def _restore_target_database_path(
        self,
        validation: BackupValidationResult,
    ) -> Path:
        manifest = validation.manifest
        if (
            self.config_file is None
            or manifest is None
            or manifest.config_filename is None
        ):
            return self.database_path

        config_path = validation.backup_path / manifest.config_filename
        if not _regular_file_inside(config_path, validation.backup_path):
            return self.database_path

        project_root = self.config_file.resolve().parent.parent
        restored_config = load_config(project_root=project_root, config_path=config_path)
        return restored_config.paths.database_path

    def _new_backup_id(self, created_at: datetime) -> str:
        for _ in range(100):
            backup_id = f"{self._timestamp_for_id(created_at)}_{self._uuid_suffix()}"
            if not self._path_for_backup_id(backup_id, BACKUP_DIRECTORY_PREFIX).exists():
                return backup_id
        raise BackupError("A unique backup ID could not be generated.")

    def _timestamp_for_id(self, created_at: datetime) -> str:
        return created_at.strftime("%Y%m%dT%H%M%SZ")

    def _created_at_iso(self, created_at: datetime) -> str:
        return created_at.isoformat(timespec="seconds").replace("+00:00", "Z")

    def _now_utc(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _uuid_suffix(self) -> str:
        value = str(self.uuid_factory()).replace("-", "").lower()
        if not re.fullmatch(r"[a-f0-9]{8,}", value):
            value = uuid.uuid4().hex
        return value[:8]

    def _resolve_backup_path(self, backup_id: str) -> Path:
        text = str(backup_id).strip()
        if not _is_safe_backup_id(text):
            raise ValidationError("Backup ID is not recognized.")

        backup_path = self._path_for_backup_id(text, BACKUP_DIRECTORY_PREFIX)
        if not backup_path.is_dir():
            raise RecordNotFoundError(f"Backup was not found: {text}")
        return backup_path

    def _path_for_backup_id(self, backup_id: str, prefix: str) -> Path:
        return resolve_relative_path(self.backup_dir, f"{prefix}{backup_id}")

    def _restore_temp_path(self, prefix: str, backup_id: str) -> Path:
        return resolve_relative_path(self.temp_dir, f"{prefix}_{backup_id}.sqlite3")

    def _replace_file(self, source_path: Path, destination_path: Path) -> None:
        os.replace(source_path, destination_path)

    def _remove_file_inside(self, path: Path, root: Path) -> None:
        try:
            resolved = Path(path).resolve()
            if not resolved.is_relative_to(Path(root).resolve()):
                raise BackupError("Temporary path is outside the controlled directory.")
            if Path(path).exists():
                if not Path(path).is_file():
                    raise BackupError("Temporary path is not a file.")
                Path(path).unlink()
        except FileNotFoundError:
            return
        except (PermissionError, IsADirectoryError, NotADirectoryError, OSError) as error:
            raise BackupError("Temporary file could not be removed safely.") from error

    def _remove_directory_inside(self, path: Path, root: Path) -> None:
        try:
            resolved = Path(path).resolve()
            if not resolved.is_relative_to(Path(root).resolve()):
                raise BackupError("Temporary path is outside the controlled directory.")
            if Path(path).exists():
                if not Path(path).is_dir():
                    raise BackupError("Temporary path is not a directory.")
                shutil.rmtree(path)
        except FileNotFoundError:
            return
        except (PermissionError, NotADirectoryError, OSError) as error:
            raise BackupError("Temporary directory could not be removed safely.") from error

    def _info_from_validation(self, validation: BackupValidationResult) -> BackupInfo:
        return BackupInfo(
            backup_id=validation.backup_id,
            created_at=validation.created_at,
            schema_version=validation.schema_version,
            size_bytes=validation.database_size_bytes,
            sha256=validation.database_sha256,
            backup_path=validation.backup_path,
            database_path=validation.database_path,
            manifest_path=validation.backup_path / BACKUP_MANIFEST_FILENAME,
            reason=validation.reason,
            is_valid=validation.valid,
            validation_message=validation.message,
            migration_versions=validation.migration_versions,
        )


def _connect_read_only(database_path: Path) -> sqlite3.Connection:
    uri = f"{Path(database_path).resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _is_safe_backup_id(backup_id: str) -> bool:
    return bool(BACKUP_ID_PATTERN.fullmatch(str(backup_id)))


def _normalize_reason(reason: str) -> str:
    cleaned = " ".join(str(reason or "").strip().split())
    return (cleaned or BACKUP_REASON_MANUAL)[:80]


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """
    ).fetchall()
    return {row["name"] for row in rows}


def _migration_versions(
    connection: sqlite3.Connection,
    issues: list[str],
) -> tuple[int, ...]:
    rows = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    versions = []
    for row in rows:
        version = row["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
            issues.append("Database migration versions are not valid.")
            continue
        versions.append(version)
    return tuple(versions)


def _record_counts(connection: sqlite3.Connection) -> tuple[BackupRecordCount, ...]:
    counts = []
    for table_name in OPERATIONAL_TABLES:
        row = connection.execute(f"SELECT COUNT(*) AS row_count FROM {table_name}").fetchone()
        if row["row_count"]:
            counts.append(BackupRecordCount(table_name, row["row_count"]))
    return tuple(counts)


def _regular_file_inside(file_path: Path, root: Path) -> bool:
    try:
        resolved_file = Path(file_path).resolve()
        resolved_root = Path(root).resolve()
        is_regular_file = Path(file_path).is_file()
        is_symlink = Path(file_path).is_symlink()
    except OSError:
        return False

    return (
        resolved_file.is_relative_to(resolved_root)
        and is_regular_file
        and not is_symlink
    )


def _safe_database_path(root: Path, database_path: Path | None) -> Path | None:
    if database_path is None or not _regular_file_inside(database_path, root):
        return None
    return database_path


def _safe_database_size(root: Path, database_path: Path | None) -> int | None:
    safe_path = _safe_database_path(root, database_path)
    if safe_path is None:
        return None
    try:
        return safe_path.stat().st_size
    except OSError:
        return None


def _safe_database_sha256(root: Path, database_path: Path | None) -> str | None:
    safe_path = _safe_database_path(root, database_path)
    if safe_path is None:
        return None
    try:
        return sha256_file(safe_path)
    except BackupError:
        return None


def _manifest_from_data(
    data: dict[str, object],
    issues: list[str],
) -> BackupManifest | None:
    required_keys = {
        "application_name",
        "application_version",
        "backup_format_version",
        "backup_id",
        "created_at",
        "database_filename",
        "database_sha256",
        "database_size_bytes",
        "migration_versions",
        "reason",
    }
    missing_keys = sorted(required_keys - set(data))
    if missing_keys:
        issues.append("Backup manifest is missing field(s): " + ", ".join(missing_keys) + ".")
        return None

    backup_format_version = _required_int(data, "backup_format_version", issues)
    backup_id = _required_text(data, "backup_id", issues)
    created_at = _required_text(data, "created_at", issues)
    application_name = _required_text(data, "application_name", issues)
    application_version = _required_text(data, "application_version", issues)
    schema_version = _optional_int(data, "schema_version", issues)
    database_filename = _required_text(data, "database_filename", issues)
    database_size_bytes = _required_int(data, "database_size_bytes", issues)
    database_sha256 = _required_text(data, "database_sha256", issues)
    reason = _required_text(data, "reason", issues)
    migration_versions = _required_int_tuple(data, "migration_versions", issues)
    record_counts = _record_counts_from_manifest(data.get("record_counts", {}), issues)
    config_filename = _optional_text(data, "config_filename", issues)
    config_size_bytes = _optional_int(data, "config_size_bytes", issues)
    config_sha256 = _optional_text(data, "config_sha256", issues)

    if issues:
        return None
    if backup_format_version > BACKUP_FORMAT_VERSION:
        issues.append(
            "Unsupported backup format version "
            f"{backup_format_version}; this application supports version "
            f"{BACKUP_FORMAT_VERSION}."
        )
    if not _is_safe_backup_id(backup_id):
        issues.append("Backup manifest contains an invalid backup ID.")
    if not SHA256_PATTERN.fullmatch(database_sha256):
        issues.append("Backup manifest contains an invalid database checksum.")
    if config_sha256 is not None and not SHA256_PATTERN.fullmatch(config_sha256):
        issues.append("Backup manifest contains an invalid config checksum.")
    if database_size_bytes < 0:
        issues.append("Backup manifest contains an invalid database size.")
    if config_size_bytes is not None and config_size_bytes < 0:
        issues.append("Backup manifest contains an invalid config size.")
    if issues:
        return None

    return BackupManifest(
        backup_format_version=backup_format_version,
        backup_id=backup_id,
        created_at=created_at,
        application_name=application_name,
        application_version=application_version,
        schema_version=schema_version,
        migration_versions=migration_versions,
        database_filename=database_filename,
        database_size_bytes=database_size_bytes,
        database_sha256=database_sha256,
        reason=reason,
        record_counts=record_counts,
        config_filename=config_filename,
        config_size_bytes=config_size_bytes,
        config_sha256=config_sha256,
    )


def _manifest_matches_expected(
    manifest: BackupManifest,
    expected_backup_id: str,
    issues: list[str],
) -> bool:
    valid = True
    if manifest.backup_format_version != BACKUP_FORMAT_VERSION:
        issues.append(
            "Backup format version is not supported by this application."
        )
        valid = False
    if manifest.backup_id != expected_backup_id:
        issues.append("Backup manifest ID does not match the selected backup.")
        valid = False
    return valid


def _required_text(
    data: dict[str, object],
    key: str,
    issues: list[str],
) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        issues.append(f"Backup manifest field '{key}' must be text.")
        return ""
    return value.strip()


def _optional_text(
    data: dict[str, object],
    key: str,
    issues: list[str],
) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        issues.append(f"Backup manifest field '{key}' must be text when present.")
        return None
    return value.strip()


def _required_int(
    data: dict[str, object],
    key: str,
    issues: list[str],
) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        issues.append(f"Backup manifest field '{key}' must be an integer.")
        return 0
    return value


def _optional_int(
    data: dict[str, object],
    key: str,
    issues: list[str],
) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        issues.append(f"Backup manifest field '{key}' must be an integer when present.")
        return None
    return value


def _required_int_tuple(
    data: dict[str, object],
    key: str,
    issues: list[str],
) -> tuple[int, ...]:
    value = data.get(key)
    if not isinstance(value, list):
        issues.append(f"Backup manifest field '{key}' must be a list.")
        return ()
    versions = []
    for item in value:
        if not isinstance(item, int) or isinstance(item, bool):
            issues.append(f"Backup manifest field '{key}' must contain integers.")
            return ()
        versions.append(item)
    return tuple(versions)


def _record_counts_from_manifest(
    value: object,
    issues: list[str],
) -> tuple[BackupRecordCount, ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        issues.append("Backup manifest field 'record_counts' must be an object.")
        return ()

    counts = []
    for table_name in OPERATIONAL_TABLES:
        row_count = value.get(table_name)
        if row_count is None:
            continue
        if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0:
            issues.append("Backup manifest record counts must be non-negative integers.")
            return ()
        counts.append(BackupRecordCount(table_name, row_count))
    return tuple(counts)
