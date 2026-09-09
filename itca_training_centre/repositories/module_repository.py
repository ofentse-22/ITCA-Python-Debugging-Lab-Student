"""Persistence operations for course modules."""

from pathlib import Path
import sqlite3

from ..data.connection import open_database, transaction
from ..models.module import (
    MODULE_ACTIVE_STATUS,
    MODULE_ARCHIVED_STATUS,
    MODULE_STATUSES,
    Module,
)
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)


MODULE_COLUMNS = """
module_id,
course_id,
module_code,
module_name,
sequence_number,
status
"""

MODULE_ORDER_BY = "sequence_number, lower(module_code)"


class ModuleRepository:
    """SQLite-backed repository for course module records."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def create(
        self,
        course_id: int,
        module_code: str,
        module_name: str,
        sequence_number: int,
        status: str = MODULE_ACTIVE_STATUS,
    ) -> Module:
        """Insert and return a module for an existing course."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        INSERT INTO modules (
                            course_id,
                            module_code,
                            module_name,
                            sequence_number,
                            status
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            sequence_number,
                            module_code,
                            module_name,
                            course_id,
                            status,
                        ),
                    )
                    module_id = cursor.lastrowid

                return self._get_by_id_in_connection(connection, module_id)
        except sqlite3.IntegrityError as error:
            raise _module_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Module could not be created.") from error

    def get_by_id(self, module_id: int) -> Module | None:
        """Return a module by primary key, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                return self._get_optional_by_id_in_connection(connection, module_id)
        except sqlite3.Error as error:
            raise DatabaseError("Module could not be retrieved.") from error

    def get_by_course_and_code(
        self,
        course_id: int,
        module_code: str,
    ) -> Module | None:
        """Return a module by its course and module code."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT {MODULE_COLUMNS}
                    FROM modules
                    WHERE course_id = ?
                      AND module_code = ?
                    """,
                    (course_id, module_code),
                ).fetchone()

            return _module_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Module could not be retrieved.") from error

    def list_for_course(
        self,
        course_id: int,
        include_archived: bool = False,
        status: str | None = None,
    ) -> list[Module]:
        """Return modules for one course in sequence order."""
        where_parts = ["course_id = ?"]
        parameters: list[int | str] = [course_id]
        _append_module_status_filter(where_parts, parameters, include_archived, status)

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT {MODULE_COLUMNS}
                    FROM module
                    WHERE {" AND ".join(where_parts)}
                    ORDER BY {MODULE_ORDER_BY}
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_module_from_row(row) for row in rows]
        except sqlite3.OperationalError as error:
            raise ValidationError("Module list filters are not valid.") from error
        except sqlite3.Error as error:
            raise DatabaseError("Modules could not be listed.") from error

    def search(
        self,
        search_text: str,
        course_id: int | None = None,
        include_archived: bool = False,
        status: str | None = None,
    ) -> list[Module]:
        """Search modules by code or name, optionally inside one course."""
        pattern = _like_pattern(search_text)
        where_parts = [
            """
            (
                module_code LIKE ? ESCAPE '\\'
                OR module_name LIKE ? ESCAPE '\\'
            )
            """
        ]
        parameters: list[int | str] = [pattern, pattern]

        if course_id is not None:
            where_parts.append("course_id = ?")
            parameters.append(course_id)

        _append_module_status_filter(where_parts, parameters, include_archived, status)

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT {MODULE_COLUMNS}
                    FROM modules
                    WHERE {" AND ".join(where_parts)}
                    ORDER BY course_id, {MODULE_ORDER_BY}
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_module_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Modules could not be searched.") from error

    def update(
        self,
        module_id: int,
        module_name: str,
        sequence_number: int,
        status: str,
    ) -> Module | None:
        """Update mutable module fields and return the updated module."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE modules
                        SET module_name = ?,
                            sequence_number = ?,
                            status = ?
                        WHERE module_id = ?
                        """,
                        (module_name, sequence_number, status, module_id),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, module_id)
        except sqlite3.IntegrityError as error:
            raise _module_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Module could not be updated.") from error

    def deactivate(self, module_id: int) -> Module | None:
        """Archive a module without physically deleting the record."""
        return self._set_status(module_id, MODULE_ARCHIVED_STATUS)

    def reactivate(self, module_id: int) -> Module | None:
        """Set a module back to active using the same stored record."""
        return self._set_status(module_id, MODULE_ACTIVE_STATUS)

    def _set_status(self, module_id: int, status: str) -> Module | None:
        if status not in MODULE_STATUSES:
            raise ValueError(f"Unsupported module status: {status}")

        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE modules
                        SET status = ?
                        WHERE module_id = ?
                        """,
                        (status, module_id),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, module_id)
        except sqlite3.Error as error:
            raise DatabaseError("Module status could not be changed.") from error

    def _get_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        module_id: int,
    ) -> Module:
        module = self._get_optional_by_id_in_connection(connection, module_id)
        if module is None:
            raise DatabaseError("Created module could not be retrieved.")

        return module

    def _get_optional_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        module_id: int,
    ) -> Module | None:
        row = connection.execute(
            f"""
            SELECT {MODULE_COLUMNS}
            FROM modules
            WHERE module_id = ?
            """,
            (module_id,),
        ).fetchone()
        return _module_from_row(row) if row is not None else None


def _module_from_row(row) -> Module:
    return Module(
        module_id=row["module_id"],
        course_id=row["course_id"],
        module_code=row["module_code"],
        module_name=row["module_name"],
        sequence_number=row["sequence_number"],
        status=row["status"],
    )


def _module_constraint_error(error: sqlite3.IntegrityError):
    message = str(error)
    if "modules.course_id, modules.module_code" in message:
        return DuplicateRecordError("Module code already exists for this course.")
    if "modules.course_id, modules.sequence_number" in message:
        return DuplicateRecordError("Module sequence already exists for this course.")
    if "FOREIGN KEY constraint failed" in message:
        return RecordNotFoundError("Course was not found for this module operation.")

    return DatabaseError("Module data violated a database constraint.")


def _append_module_status_filter(
    where_parts: list[str],
    parameters: list[int | str],
    include_archived: bool,
    status: str | None,
) -> None:
    if status is not None:
        where_parts.append("status = ?")
        parameters.append(status)
    elif not include_archived:
        where_parts.append("status = ?")
        parameters.append(MODULE_ACTIVE_STATUS)


def _like_pattern(search_text: str) -> str:
    escaped = (
        search_text.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"
