"""Persistence operations for course enrolments."""

from pathlib import Path
import sqlite3

from ..data.connection import open_database, transaction
from ..models.course_enrolment import (
    ENROLMENT_ACTIVE_STATUS,
    ENROLMENT_CANCELLED_STATUS,
    ENROLMENT_STATUSES,
    CourseEnrolment,
)
from ..utils.exceptions import DatabaseError, DuplicateRecordError, RecordNotFoundError


ENROLMENT_COLUMNS = """
enrolment_id,
student_id,
course_id,
enrolment_date,
status,
cancelled_at,
cancellation_reason,
created_at,
updated_at
"""


class CourseEnrolmentRepository:
    """SQLite-backed repository for course enrolment records."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def create(
        self,
        student_id: int,
        course_id: int,
        enrolment_date: str,
        status: str = ENROLMENT_ACTIVE_STATUS,
    ) -> CourseEnrolment:
        """Insert and return a student-course enrolment."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        INSERT INTO course_enrolments (
                            student_id,
                            course_id,
                            enrolment_date,
                            status
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (student_id, course_id, enrolment_date, status),
                    )
                    enrolment_id = cursor.lastrowid

                return self._get_by_id_in_connection(connection, enrolment_id)
        except sqlite3.IntegrityError as error:
            raise _enrolment_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Course enrolment could not be created.") from error

    def get_by_id(self, enrolment_id: int) -> CourseEnrolment | None:
        """Return an enrolment by primary key, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                return self._get_optional_by_id_in_connection(connection, enrolment_id)
        except sqlite3.Error as error:
            raise DatabaseError("Course enrolment could not be retrieved.") from error

    def get_active_for_student_course(
        self,
        student_id: int,
        course_id: int,
    ) -> CourseEnrolment | None:
        """Return the active enrolment for one student/course pair."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT {ENROLMENT_COLUMNS}
                    FROM course_enrolments
                    WHERE student_id = ?
                      AND course_id = ?
                      AND status = ?
                    """,
                    (student_id, course_id, ENROLMENT_ACTIVE_STATUS),
                ).fetchone()

            return _enrolment_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Course enrolment could not be retrieved.") from error

    def list_enrolments(
        self,
        include_historical: bool = False,
        status: str | None = None,
    ) -> list[CourseEnrolment]:
        """Return enrolments in a deterministic cross-course order."""
        where_parts: list[str] = []
        parameters: list[str] = []
        _append_enrolment_status_filter(where_parts, parameters, include_historical, status)

        return self._list_joined(
            where_parts=where_parts,
            parameters=parameters,
            order_by=(
                "lower(c.course_code), lower(s.last_name), "
                "lower(s.first_name), lower(s.student_number), "
                "e.enrolment_date, e.enrolment_id"
            ),
        )

    def list_for_student(
        self,
        student_id: int,
        include_historical: bool = False,
        status: str | None = None,
    ) -> list[CourseEnrolment]:
        """Return enrolments for one student ordered by course and date."""
        where_parts = ["e.student_id = ?"]
        parameters: list[int | str] = ["student_id"]
        _append_enrolment_status_filter(where_parts, parameters, include_historical, status)

        return self._list_joined(
            where_parts=where_parts,
            parameters=parameters,
            order_by="lower(c.course_code), e.enrolment_date, e.enrolment_id",
        )

    def list_for_course(
        self,
        course_id: int,
        include_historical: bool = False,
        status: str | None = None,
    ) -> list[CourseEnrolment]:
        """Return enrolments for one course ordered by student name."""
        where_parts = ["e.course_id = ?"]
        parameters: list[int | str] = [course_id]
        _append_enrolment_status_filter(where_parts, parameters, include_historical, status)

        return self._list_joined(
            where_parts=where_parts,
            parameters=parameters,
            order_by=(
                "lower(s.last_name), lower(s.first_name), "
                "lower(s.student_number), e.enrolment_date, e.enrolment_id"
            ),
        )

    def list_for_student_course(
        self,
        student_id: int,
        course_id: int,
        include_historical: bool = False,
        status: str | None = None,
    ) -> list[CourseEnrolment]:
        """Return enrolments for one student/course pair ordered by date."""
        where_parts = ["e.student_id = ?", "e.course_id = ?"]
        parameters: list[int | str] = [student_id, course_id]
        _append_enrolment_status_filter(where_parts, parameters, include_historical, status)

        return self._list_joined(
            where_parts=where_parts,
            parameters=parameters,
            order_by="e.enrolment_date, e.enrolment_id",
        )

    def cancel(
        self,
        enrolment_id: int,
        cancelled_at: str,
        cancellation_reason: str,
    ) -> CourseEnrolment | None:
        """Cancel an enrolment while preserving the historical row."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE course_enrolments
                        SET status = ?,
                            cancelled_at = ?,
                            cancellation_reason = ?,
                            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        WHERE enrolment_id = ?
                        """,
                        (
                            ENROLMENT_CANCELLED_STATUS,
                            cancelled_at,
                            cancellation_reason,
                            enrolment_id,
                        ),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, enrolment_id)
        except sqlite3.Error as error:
            raise DatabaseError("Course enrolment could not be cancelled.") from error

    def _list_joined(
        self,
        where_parts: list[str],
        parameters: list[int | str],
        order_by: str,
    ) -> list[CourseEnrolment]:
        where_clause = ""
        if where_parts:
            where_clause = f"WHERE {' AND '.join(where_parts)}"

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        e.enrolment_id,
                        e.student_id,
                        e.course_id,
                        e.enrolment_date,
                        e.status,
                        e.cancelled_at,
                        e.cancellation_reason,
                        e.created_at,
                        e.updated_at
                    FROM course_enrolments e
                    JOIN students s ON s.student_id = e.student_id
                    JOIN courses c ON c.course_id = e.course_id
                    {where_clause}
                    ORDER BY {order_by}
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_enrolment_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Course enrolments could not be listed.") from error

    def _get_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        enrolment_id: int,
    ) -> CourseEnrolment:
        enrolment = self._get_optional_by_id_in_connection(connection, enrolment_id)
        if enrolment is None:
            raise DatabaseError("Created course enrolment could not be retrieved.")

        return enrolment

    def _get_optional_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        enrolment_id: int,
    ) -> CourseEnrolment | None:
        row = connection.execute(
            f"""
            SELECT {ENROLMENT_COLUMNS}
            FROM course_enrolments
            WHERE enrolment_id = ?
            """,
            (enrolment_id,),
        ).fetchone()
        return _enrolment_from_row(row) if row is not None else None


def _enrolment_from_row(row) -> CourseEnrolment:
    return CourseEnrolment(
        enrolment_id=row["enrolment_id"],
        student_id=row["student_id"],
        course_id=row["course_id"],
        enrolment_date=row["enrolment_date"],
        status=row["status"],
        cancelled_at=row["cancelled_at"],
        cancellation_reason=row["cancellation_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _enrolment_constraint_error(error: sqlite3.IntegrityError):
    message = str(error)
    if "course_enrolments.student_id, course_enrolments.course_id" in message:
        return DuplicateRecordError("Student is already actively enrolled in this course.")
    if "FOREIGN KEY constraint failed" in message:
        return RecordNotFoundError(
            "Student or course was not found for this enrolment operation."
        )

    return DatabaseError("Course enrolment data violated a database constraint.")


def _append_enrolment_status_filter(
    where_parts: list[str],
    parameters: list[int | str],
    include_historical: bool,
    status: str | None,
) -> None:
    if status is not None:
        where_parts.append("e.status = ?")
        parameters.append(status)
    elif not include_historical:
        where_parts.append("e.status = ?")
        parameters.append(ENROLMENT_ACTIVE_STATUS)
