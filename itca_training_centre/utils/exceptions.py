"""Custom exceptions used by the clean application."""


class TrainingCentreError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(TrainingCentreError):
    """Raised when configuration cannot be loaded or validated."""


class PathSafetyError(TrainingCentreError):
    """Raised when a path would leave a controlled application directory."""


class LoggingSetupError(TrainingCentreError):
    """Raised when application logging cannot be initialized."""


class DatabaseError(TrainingCentreError):
    """Base class for expected database infrastructure errors."""


class DatabaseConnectionError(DatabaseError):
    """Raised when a SQLite connection cannot be opened or configured."""


class MigrationError(DatabaseError):
    """Raised when database schema migration fails."""


class UnsupportedSchemaVersionError(DatabaseError):
    """Raised when the database is newer than this application supports."""


class ValidationError(TrainingCentreError):
    """Raised when user or domain input is not valid."""


class DuplicateRecordError(TrainingCentreError):
    """Raised when a record would violate a uniqueness rule."""


class RecordNotFoundError(TrainingCentreError):
    """Raised when an expected record does not exist."""


class ImportExportError(TrainingCentreError):
    """Base class for expected import/export workflow errors."""


class ImportValidationError(ImportExportError):
    """Raised when an import file cannot be parsed or validated."""


class ExportFileError(ImportExportError):
    """Raised when an export file cannot be written safely."""


class BackupError(TrainingCentreError):
    """Base class for expected backup workflow errors."""


class BackupValidationError(Exception):
    """Raised when a backup package fails validation."""


class RestoreError(BackupError):
    """Raised when a restore workflow cannot complete safely."""
