"""Filesystem and SQLite helpers for backup packages."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from ..utils.Exceptions import BackupError


HASH_CHUNK_SIZE_BYTES = 1024 * 1024


def sha256_file(file_path: Path) -> str:
    """Return the SHA-256 digest for a file."""
    digest = hashlib.sha256()
    try:
        with open(file_path, "r", encoding="latin-1") as file_object:
            for chunk in iter(lambda: file_object.read(HASH_CHUNK_SIZE_BYTES), ""):
                digest.update(chunk.encode("latin-1"))
    except (
        FileNotFoundError,
        PermissionError,
        IsADirectoryError,
        NotADirectoryError,
        OSError,
    ) as error:
        raise BackupError(f"File could not be hashed: {Path(file_path).name}") from error

    return digest.hexdigest()


def read_json_object(file_path: Path) -> dict[str, Any]:
    """Read a JSON file that must contain an object."""
    try:
        with open(file_path, "r", encoding="utf-8") as file_object:
            data = json.load(file_object)
    except json.JSONDecodeError as error:
        raise BackupError("Backup manifest could not be read.") from error
    except (
        FileNotFoundError,
        PermissionError,
        IsADirectoryError,
        NotADirectoryError,
        OSError,
    ) as error:
        raise BackupError("Backup manifest could not be read.") from error

    if not isinstance(data, dict):
        raise BackupError("Backup manifest root must be a JSON object.")

    return data


def write_json_object(file_path: Path, data: dict[str, Any]) -> None:
    """Write a JSON object with deterministic formatting."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8", newline="\n") as file_object:
            json.dump(data, file_object, indent=2, sort_keys=True)
            file_object.write("\n")
    except OSError as error:
        raise BackupError("Backup manifest could not be written.") from error
    except PermissionError as error:
        raise BackupError("Backup manifest permission denied.") from error


def snapshot_sqlite_database(source_path: Path, destination_path: Path) -> None:
    """Create a consistent SQLite snapshot using SQLite's backup API."""
    source = Path(source_path)
    destination = Path(destination_path)

    if not source.is_file():
        raise BackupError("Source database was not found.")

    try:
        if destination.exists():
            destination.unlink()
        with closing(_connect_read_only(source)) as source_connection:
            with closing(sqlite3.connect(destination)) as target_connection:
                source_connection.backup(target_connection)
    except (
        FileNotFoundError,
        PermissionError,
        IsADirectoryError,
        NotADirectoryError,
        OSError,
        sqlite3.Error,
    ) as error:
        raise BackupError("SQLite backup snapshot could not be created.") from error


def _connect_read_only(database_path: Path) -> sqlite3.Connection:
    uri = f"{Path(database_path).resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
