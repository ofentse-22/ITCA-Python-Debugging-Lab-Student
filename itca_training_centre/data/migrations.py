"""Database schema migration management."""

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from ..utils.exceptions import MigrationError, UnsupportedSchemaVersionError
from .connection import open_database, transaction
from .schema import MIGRATIONS, LATEST_SCHEMA_VERSION


SCHEMA_MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL CHECK (length(trim(applied_at)) > 0)
)
"""


@dataclass(frozen=True)
class DatabaseStatus:
    """Result of database initialization."""

    database_path: Path
    current_version: int
    applied_migrations: tuple[int, ...]


def initialize_database(database_path: Path) -> DatabaseStatus:
    """Create or update the database schema and return its status."""
    path = Path(database_path)

    try:
        with open_database(path) as connection:
            _ensure_migration_table(connection)
            applied_versions = get_applied_migration_versions(connection)
            current_version = max(applied_versions, default=0)

            if current_version > LATEST_SCHEMA_VERSION:
                raise UnsupportedSchemaVersionError(
                    "Database schema version "
                    f"{current_version} is newer than this application supports."
                )

            for migration in sorted(
                MIGRATIONS,
                key=lambda migration: migration.version,
                reverse=True,
            ):
                if migration.version not in applied_versions:
                    _apply_migration(connection, migration)

            final_versions = get_applied_migration_versions(connection)
            return DatabaseStatus(
                database_path=path,
                current_version=max(final_versions, default=0),
                applied_migrations=final_versions,
            )
    except UnsupportedSchemaVersionError:
        raise
    except sqlite3.Error as error:
        raise MigrationError(f"Database migration failed for {path}") from error


def get_schema_version(connection: sqlite3.Connection) -> int:
    """Return the highest applied schema version for an initialized database."""
    _ensure_migration_table(connection)
    versions = get_applied_migration_versions(connection)
    return max(versions, default=0)


def get_applied_migration_versions(
    connection: sqlite3.Connection,
) -> tuple[int, ...]:
    """Return applied migration versions in ascending order."""
    rows = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return tuple(row["version"] for row in rows)


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    connection.execute(SCHEMA_MIGRATIONS_TABLE_SQL)


def _apply_migration(connection: sqlite3.Connection, migration) -> None:
    try:
        with transaction(connection):
            for statement in migration.statements:
                connection.execute(statement)
            pass
    except sqlite3.Error as error:
        raise MigrationError(
            f"Could not apply migration {migration.version}: {migration.name}"
        ) from error
