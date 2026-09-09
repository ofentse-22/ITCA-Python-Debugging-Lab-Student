"""Persistence operations for assessments."""

from decimal import Decimal
from pathlib import Path
import sqlite3

from ..data.connection import open_database, transaction
from ..data.decimal_storage import decimal_from_storage, decimal_to_storage
from ..models.assessment import (
    ASSESSMENT_ACTIVE_STATUS,
    ASSESSMENT_ARCHIVED_STATUS,
    ASSESSMENT_STATUSES,
    Assessment,
)
from ..utils.exceptions import DatabaseError, RecordNotFoundError


ASSESSMENT_COLUMNS = """
assessment_id,
course_id,
module_id,
assessment_name,
assessment_type,
max_mark,
weight,
pass_mark,
status,
created_at,
updated_at
"""

ASSESSMENT_ORDER_BY = """
lower(c.course_code),
CASE WHEN a.module_id IS NULL THEN 0 ELSE 1 END,
COALESCE(m.sequence_number, 0),
lower(COALESCE(m.module_code, '')),
lower(a.assessment_name),
a.assessment_id
"""


class AssessmentRepository:
    """SQLite-backed repository for assessment definitions."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def create(
        self,
        course_id: int,
        module_id: int | None,
        assessment_name: str,
        assessment_type: str,
        max_mark: Decimal,
        weight: Decimal | None = None,
        pass_mark: Decimal | None = None,
        status: str = ASSESSMENT_ACTIVE_STATUS,
    ) -> Assessment:
        """Insert and return a new assessment."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        INSERT INTO assessments (
                            course_id,
                            module_id,
                            assessment_name,
                            assessment_type,
                            max_mark,
                            weight,
                            pass_mark,
                            status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            course_id,
                            module_id,
                            assessment_name,
                            assessment_type,
                            decimal_to_storage(max_mark),
                            _optional_decimal_to_storage(weight),
                            _optional_decimal_to_storage(pass_mark),
                            status,
                        ),
                    )
                    assessment_id = cursor.lastrowid

                return self._get_by_id_in_connection(connection, assessment_id)
        except sqlite3.IntegrityError as error:
            raise _assessment_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Assessment could not be created.") from error
        except (TypeError, ValueError) as error:
            raise DatabaseError("Assessment Decimal value could not be stored.") from error

    def get_by_id(self, assessment_id: int) -> Assessment | None:
        """Return an assessment by primary key, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                return self._get_optional_by_id_in_connection(connection, assessment_id)
        except sqlite3.Error as error:
            raise DatabaseError("Assessment could not be retrieved.") from error

    def list_assessments(
        self,
        course_id: int | None = None,
        module_id: int | None = None,
        include_archived: bool = False,
        status: str | None = None,
        assessment_type: str | None = None,
    ) -> list[Assessment]:
        """Return assessments using optional supported filters."""
        where_parts: list[str] = []
        parameters: list[int | str] = []

        if course_id is not None:
            where_parts.append("a.course_id = ?")
            parameters.append(course_id)
        if module_id is not None:
            where_parts.append("a.module_id = ?")
            parameters.append(module_id)
        if assessment_type is not None:
            where_parts.append("a.assessment_type = ?")
            parameters.append(assessment_type)

        _append_assessment_status_filter(
            where_parts,
            parameters,
            include_archived,
            status,
        )

        return self._list_joined(where_parts, parameters)

    def list_for_course(
        self,
        course_id: int,
        include_archived: bool = False,
        status: str | None = None,
    ) -> list[Assessment]:
        """Return assessments for one course."""
        return self.list_assessments(
            course_id=course_id,
            include_archived=include_archived,
            status=status,
        )

    def list_for_module(
        self,
        module_id: int,
        include_archived: bool = False,
        status: str | None = None,
    ) -> list[Assessment]:
        """Return assessments for one module."""
        return self.list_assessments(
            module_id=module_id,
            include_archived=include_archived,
            status=status,
        )

    def search(
        self,
        search_text: str,
        course_id: int | None = None,
        module_id: int | None = None,
        include_archived: bool = False,
        status: str | None = None,
        assessment_type: str | None = None,
    ) -> list[Assessment]:
        """Search assessments by title, type, course, module, status, or timestamp."""
        pattern = _like_pattern(search_text)
        where_parts = [
            """
            (
                a.assessment_name LIKE ? ESCAPE '\\'
                OR a.assessment_type LIKE ? ESCAPE '\\'
                OR a.status LIKE ? ESCAPE '\\'
                OR a.created_at LIKE ? ESCAPE '\\'
                OR c.course_code LIKE ? ESCAPE '\\'
                OR c.course_name LIKE ? ESCAPE '\\'
                OR COALESCE(m.module_code, '') LIKE ? ESCAPE '\\'
                OR COALESCE(m.module_name, '') LIKE ? ESCAPE '\\'
            )
            """
        ]
        parameters: list[int | str] = [
            pattern,
            pattern,
            pattern,
            pattern,
            pattern,
            pattern,
            pattern,
            pattern,
        ]

        if course_id is not None:
            where_parts.append("a.course_id = ?")
            parameters.append(course_id)
        if module_id is not None:
            where_parts.append("a.module_id = ?")
            parameters.append(module_id)
        if assessment_type is not None:
            where_parts.append("a.assessment_type = ?")
            parameters.append(assessment_type)

        _append_assessment_status_filter(
            where_parts,
            parameters,
            include_archived,
            status,
        )

        return self._list_joined(where_parts, parameters)

    def update(
        self,
        assessment_id: int,
        assessment_name: str,
        assessment_type: str,
        max_mark: Decimal,
        weight: Decimal | None,
        pass_mark: Decimal | None,
        status: str,
    ) -> Assessment | None:
        """Update mutable assessment fields and return the updated assessment."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE assessments
                        SET assessment_name = ?,
                            assessment_type = ?,
                            max_mark = ?,
                            weight = ?,
                            pass_mark = ?,
                            status = ?,
                            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        WHERE assessment_id = ?
                        """,
                        (
                            assessment_name,
                            assessment_type,
                            decimal_to_storage(max_mark),
                            _optional_decimal_to_storage(weight),
                            _optional_decimal_to_storage(pass_mark),
                            status,
                            assessment_id,
                        ),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, assessment_id)
        except sqlite3.IntegrityError as error:
            raise _assessment_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Assessment could not be updated.") from error
        except (TypeError, ValueError) as error:
            raise DatabaseError("Assessment Decimal value could not be stored.") from error

    def deactivate(self, assessment_id: int) -> Assessment | None:
        """Archive an assessment without physically deleting the record."""
        return self._set_status(assessment_id, ASSESSMENT_ARCHIVED_STATUS)

    def reactivate(self, assessment_id: int) -> Assessment | None:
        """Set an assessment back to active using the same stored record."""
        return self._set_status(assessment_id, ASSESSMENT_ACTIVE_STATUS)

    def _set_status(self, assessment_id: int, status: str) -> Assessment | None:
        if status not in ASSESSMENT_STATUSES:
            raise ValueError(f"Unsupported assessment status: {status}")

        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE assessments
                        SET status = ?,
                            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        WHERE assessment_id = ?
                        """,
                        (status, assessment_id),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, assessment_id)
        except sqlite3.Error as error:
            raise DatabaseError("Assessment status could not be changed.") from error

    def _list_joined(
        self,
        where_parts: list[str],
        parameters: list[int | str],
    ) -> list[Assessment]:
        where_clause = ""
        if where_parts:
            where_clause = f"WHERE {' AND '.join(where_parts)}"

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        a.assessment_id,
                        a.course_id,
                        a.module_id,
                        a.assessment_name,
                        a.assessment_type,
                        a.max_mark,
                        a.weight,
                        a.pass_mark,
                        a.status,
                        a.created_at,
                        a.updated_at
                    FROM assessments a
                    JOIN courses c ON c.course_id = a.course_id
                    LEFT JOIN modules m ON m.module_id = a.module_id
                    {where_clause}
                    ORDER BY {ASSESSMENT_ORDER_BY}
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_assessment_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Assessments could not be listed.") from error

    def _get_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        assessment_id: int,
    ) -> Assessment:
        assessment = self._get_optional_by_id_in_connection(connection, assessment_id)
        if assessment is None:
            raise DatabaseError("Created assessment could not be retrieved.")

        return assessment

    def _get_optional_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        assessment_id: int,
    ) -> Assessment | None:
        row = connection.execute(
            f"""
            SELECT {ASSESSMENT_COLUMNS}
            FROM assessments
            WHERE assessment_id = ?
            """,
            (assessment_id,),
        ).fetchone()
        return _assessment_from_row(row) if row is not None else None


def _assessment_from_row(row) -> Assessment:
    return Assessment(
        assessment_id=row["assessment_id"],
        course_id=row["course_id"],
        module_id=row["module_id"],
        assessment_name=row["assessment_name"],
        assessment_type=row["assessment_type"],
        max_mark=decimal_from_storage(row["max_mark"]),
        weight=_optional_decimal_from_storage(row["weight"]),
        pass_mark=_optional_decimal_from_storage(row["pass_mark"]),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _optional_decimal_to_storage(value: Decimal | None) -> str | None:
    if value is None:
        return None

    return decimal_to_storage(value.quantize(Decimal("0.01")))


def _optional_decimal_from_storage(value: str | None) -> Decimal | None:
    if value is None:
        return None

    return decimal_from_storage(value)


def _assessment_constraint_error(error: sqlite3.IntegrityError):
    if "FOREIGN KEY constraint failed" in str(error):
        return RecordNotFoundError(
            "Course or module was not found for this assessment operation."
        )

    return DatabaseError("Assessment data violated a database constraint.")


def _append_assessment_status_filter(
    where_parts: list[str],
    parameters: list[int | str],
    include_archived: bool,
    status: str | None,
) -> None:
    if status is not None:
        where_parts.append("a.status = ?")
        parameters.append(status)
    elif not include_archived:
        where_parts.append("a.status = ?")
        parameters.append(ASSESSMENT_ACTIVE_STATUS)


def _like_pattern(search_text: str) -> str:
    escaped = (
        search_text.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"
