"""Persistence operations for students."""

from pathlib import Path
import sqlite3

from ..data.connection import open_database, transaction
from ..models.student import ACTIVE_STATUS, INACTIVE_STATUS, STUDENT_STATUSES, Student
from ..utils.exceptions import DatabaseError, DuplicateRecordError, RecordNotFoundError


STUDENT_COLUMNS = """
student_id,
student_number,
first_name,
last_name,
email,
phone,
status,
created_at,
updated_at,
archived_at
"""

STUDENT_ORDER_BY = "lower(last_name), lower(first_name), lower(student_number)"


class StudentRepository:
    """SQLite-backed repository for student records."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def create(
        self,
        student_number: str,
        first_name: str,
        last_name: str,
        email: str | None,
        phone: str | None,
    ) -> Student:
        """Insert and return a new active student."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        INSERT INTO students (
                            student_number,
                            first_name,
                            last_name,
                            email,
                            phone,
                            status
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            student_number,
                            first_name,
                            last_name,
                            email,
                            phone,
                            ACTIVE_STATUS,
                        ),
                    )
                    student_id = cursor.lastrowid

                return self._get_by_id_in_connection(connection, student_id)
        except sqlite3.IntegrityError as error:
            raise _duplicate_error_from_integrity_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Student could not be created.") from error

    def get_by_id(self, student_id: int) -> Student | None:
        """Return a student by primary key, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                return self._get_optional_by_id_in_connection(connection, student_id)
        except sqlite3.Error as error:
            raise DatabaseError("Student could not be retrieved.") from error

    def get_by_student_number(self, student_number: str) -> Student | None:
        """Return a student by student number, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT {STUDENT_COLUMNS}
                    FROM students
                    WHERE student_number = ?
                    """,
                    (student_number,),
                ).fetchone()

            return _student_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Student could not be retrieved.") from error

    def list_students(self, include_inactive: bool = False) -> list[Student]:
        """Return students in deterministic display order."""
        try:
            with open_database(self.database_path) as connection:
                if include_inactive:
                    rows = connection.execute(
                        f"""
                        SELECT {STUDENT_COLUMNS}
                        FROM students
                        ORDER BY {STUDENT_ORDER_BY}
                        """
                    ).fetchall()
                else:
                    rows = connection.execute(
                        f"""
                        SELECT {STUDENT_COLUMNS}
                        FROM students
                        WHERE status = ?
                        ORDER BY {STUDENT_ORDER_BY}
                        """,
                        (ACTIVE_STATUS,),
                    ).fetchall()

            return [_student_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Students could not be listed.") from error

    def search(self, search_text: str, include_inactive: bool = False) -> list[Student]:
        """Search by student number, name, combined name, or email."""
        pattern = "__blank_search__" if not search_text else _like_pattern(search_text)
        where_clause = """
            (
                student_number LIKE ? ESCAPE '\\'
                OR first_name LIKE ? ESCAPE '\\'
                OR last_name LIKE ? ESCAPE '\\'
                OR (first_name || ' ' || last_name) LIKE ? ESCAPE '\\'
                OR COALESCE(email, '') LIKE ? ESCAPE '\\'
            )
        """
        parameters: list[str] = [pattern, pattern, pattern, pattern, pattern]

        if not include_inactive:
            where_clause += " AND status = ?"
            parameters.append(ACTIVE_STATUS)

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT {STUDENT_COLUMNS}
                    FROM students
                    WHERE {where_clause}
                    ORDER BY {STUDENT_ORDER_BY}
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_student_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Students could not be searched.") from error

    def update(
        self,
        student_id: int,
        first_name: str,
        last_name: str,
        email: str | None,
        phone: str | None,
    ) -> Student | None:
        """Update mutable student fields and return the updated student."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE students
                        SET first_name = ?,
                            last_name = ?,
                            email = ?,
                            phone = ?,
                            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        WHERE student_id = ?
                        """,
                        (first_name, last_name, email, phone, student_id),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, student_id)
        except sqlite3.IntegrityError as error:
            raise _duplicate_error_from_integrity_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Student could not be updated.") from error

    def deactivate(self, student_id: int) -> Student | None:
        """Mark a student inactive without physically deleting the record."""
        return self._set_status(student_id, INACTIVE_STATUS)

    def reactivate(self, student_id: int) -> Student | None:
        """Mark a student active again using the same stored record."""
        return self._set_status(student_id, ACTIVE_STATUS)

    def _set_status(self, student_id: int, status: str) -> Student | None:
        if status not in STUDENT_STATUSES:
            raise ValueError(f"Unsupported student status: {status}")

        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE students
                        SET status = ?,
                            archived_at = CASE WHEN ? = 'active' THEN NULL ELSE archived_at END,
                            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        WHERE student_id = ?
                        """,
                        (status, status, student_id),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, student_id)
        except sqlite3.Error as error:
            raise DatabaseError("Student status could not be changed.") from error

    def _get_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        student_id: int,
    ) -> Student:
        student = self._get_optional_by_id_in_connection(connection, student_id)
        if student is None:
            raise DatabaseError("Created student could not be retrieved.")

        return student

    def _get_optional_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        student_id: int,
    ) -> Student | None:
        row = connection.execute(
            f"""
            SELECT {STUDENT_COLUMNS}
            FROM students
            WHERE student_id = ?
            """,
            (student_id,),
        ).fetchone()
        return _student_from_row(row) if row is not None else None


def _student_from_row(row) -> Student:
    return Student(
        student_id=row["student_id"],
        student_number=row["student_number"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        email=row["email"],
        phone=row["phone"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        archived_at=row["archived_at"],
    )


def _duplicate_error_from_integrity_error(error: sqlite3.IntegrityError):
    message = str(error)
    if "students.student_number" in message:
        return RecordNotFoundError("Student was not found for duplicate check.")
    if "students.email" in message:
        return DuplicateRecordError("Email address already exists.")

    return DatabaseError("Student data violated a database constraint.")


def _like_pattern(search_text: str) -> str:
    escaped = (
        search_text.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return escaped
