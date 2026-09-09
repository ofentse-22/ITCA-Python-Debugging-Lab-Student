"""Persistence operations for courses."""

from decimal import Decimal
from pathlib import Path
import sqlite3

from ..data.connection import open_database, transaction
from ..data.decimal_storage import decimal_from_storage, decimal_to_storage
from ..models.course import (
    COURSE_ACTIVE_STATUS,
    COURSE_ARCHIVED_STATUS,
    COURSE_PLANNED_STATUS,
    COURSE_STATUSES,
    Course,
)
from ..utils.exceptions import DatabaseError, DuplicateRecordError


COURSE_COLUMNS = """
course_id,
course_code,
course_name,
description,
fee_amount,
status,
created_at,
updated_at
"""

COURSE_ORDER_BY = "lower(course_code)"


class CourseRepository:
    """SQLite-backed repository for course records."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def create(
        self,
        course_code: str,
        course_name: str,
        description: str | None,
        fee_amount: Decimal,
        status: str = COURSE_PLANNED_STATUS,
    ) -> Course:
        """Insert and return a new course."""
        try:
            fee_storage = decimal_to_storage(fee_amount)
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        INSERT INTO courses (
                            course_code,
                            course_name,
                            description,
                            fee_amount,
                            status
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            course_code,
                            course_name,
                            description,
                            fee_storage,
                            status,
                        ),
                    )
                    course_id = cursor.lastrowid

                return self._get_by_id_in_connection(connection, course_id)
        except sqlite3.IntegrityError as error:
            raise _course_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Course could not be created.") from error
        except (TypeError, ValueError) as error:
            raise DatabaseError("Course fee amount could not be stored.") from error

    def get_by_id(self, course_id: int) -> Course | None:
        """Return a course by primary key, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                return self._get_optional_by_id_in_connection(connection, course_id)
        except sqlite3.Error as error:
            raise DatabaseError("Course could not be retrieved.") from error

    def get_by_code(self, course_code: str) -> Course | None:
        """Return a course by course code, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT {COURSE_COLUMNS}
                    FROM courses
                    WHERE course_code = ?
                    """,
                    (course_code,),
                ).fetchone()

            return _course_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Course could not be retrieved.") from error

    def list_courses(
        self,
        include_archived: bool = False,
        status: str | None = None,
    ) -> list[Course]:
        """Return courses in deterministic display order."""
        where_clause, parameters = _course_status_filter(include_archived, status)

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT {COURSE_COLUMNS}
                    FROM courses
                    {where_clause}
                    ORDER BY {COURSE_ORDER_BY}
                    """,
                    tuple(parameters),
                )
                list(rows)
                rows = rows.fetchall()

            return [_course_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Courses could not be listed.") from error

    def search(
        self,
        search_text: str,
        include_archived: bool = False,
        status: str | None = None,
    ) -> list[Course]:
        """Search courses by code, name, or description."""
        pattern = _like_pattern(search_text)
        where_parts = [
            """
            (
                course_code LIKE ? ESCAPE '\\'
                OR course_name LIKE ? ESCAPE '\\'
                OR COALESCE(description, '') LIKE ? ESCAPE '\\'
            )
            """
        ]
        parameters: list[str] = [pattern, pattern, pattern]
        status_where, status_parameters = _course_status_filter(include_archived, status)
        if status_where:
            where_parts.append(status_where.removeprefix("WHERE "))
            parameters.extend(status_parameters)

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT {COURSE_COLUMNS}
                    FROM courses
                    WHERE {" AND ".join(where_parts)}
                    ORDER BY {COURSE_ORDER_BY}
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_course_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Courses could not be searched.") from error

    def update(
        self,
        course_id: int,
        course_name: str,
        description: str | None,
        fee_amount: Decimal,
        status: str,
    ) -> Course | None:
        """Update mutable course fields and return the updated course."""
        try:
            fee_storage = decimal_to_storage(fee_amount)
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE courses
                        SET course_name = ?,
                            description = ?,
                            fee_amount = ?,
                            status = ?,
                            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        WHERE course_id = ?
                        """,
                        (
                            course_name,
                            description,
                            fee_storage,
                            status,
                            course_id,
                        ),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, course_id)
        except sqlite3.IntegrityError as error:
            raise _course_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Course could not be updated.") from error
        except (TypeError, ValueError) as error:
            raise DatabaseError("Course fee amount could not be stored.") from error

    def deactivate(self, course_id: int) -> Course | None:
        """Archive a course without physically deleting the record."""
        return self._set_status(course_id, COURSE_ARCHIVED_STATUS)

    def reactivate(self, course_id: int) -> Course | None:
        """Set a course back to active using the same stored record."""
        return self._set_status(course_id, COURSE_ACTIVE_STATUS)

    def _set_status(self, course_id: int, status: str) -> Course | None:
        if status not in COURSE_STATUSES:
            raise ValueError(f"Unsupported course status: {status}")

        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE courses
                        SET status = ?,
                            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        WHERE course_id = ?
                        """,
                        (status, course_id),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, course_id)
        except sqlite3.Error as error:
            raise DatabaseError("Course status could not be changed.") from error

    def _get_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        course_id: int,
    ) -> Course:
        course = self._get_optional_by_id_in_connection(connection, course_id)
        if course is None:
            raise DatabaseError("Created course could not be retrieved.")

        return course

    def _get_optional_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        course_id: int,
    ) -> Course | None:
        row = connection.execute(
            f"""
            SELECT {COURSE_COLUMNS}
            FROM courses
            WHERE course_id = ?
            """,
            (course_id,),
        ).fetchone()
        return _course_from_row(row) if row is not None else None


def _course_from_row(row) -> Course:
    return Course(
        course_id=row["course_id"],
        course_code=row["course_code"],
        course_name=row["course_name"],
        description=row["description"],
        fee_amount=decimal_from_storage(row["fee_amount"]),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _course_constraint_error(error: sqlite3.IntegrityError):
    message = str(error)
    if "courses.course_code" in message:
        return DuplicateRecordError("Course code already exists.")

    return DatabaseError("Course data violated a database constraint.")


def _course_status_filter(
    include_archived: bool,
    status: str | None,
) -> tuple[str, list[str]]:
    if status is not None:
        return "WHERE status = ?", [status]
    if include_archived:
        return "", []

    return "WHERE status <> ?", [COURSE_ARCHIVED_STATUS]


def _like_pattern(search_text: str) -> str:
    escaped = (
        search_text.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"
