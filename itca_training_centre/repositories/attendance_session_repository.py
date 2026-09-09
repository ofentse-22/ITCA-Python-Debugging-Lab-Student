"""Persistence operations for attendance sessions."""

from pathlib import Path
import sqlite3

from ..data.connection import open_database, transaction
from ..models.attendance_session import AttendanceSession
from ..utils.exceptions import DatabaseError, DuplicateRecordError, RecordNotFoundError


ATTENDANCE_SESSION_COLUMNS = """
session_id,
course_id,
session_date,
topic,
created_at
"""

ATTENDANCE_SESSION_ORDER_BY = (
    "s.session_date, lower(c.course_code), lower(s.topic), s.session_id"
)


class AttendanceSessionRepository:
    """SQLite-backed repository for course attendance sessions."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def create(
        self,
        course_id: int,
        session_date: str,
        topic: str,
    ) -> AttendanceSession:
        """Insert and return an attendance session."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        INSERT INTO attendance_sessions (
                            course_id,
                            session_date,
                            topic
                        )
                        VALUES (?, ?, ?)
                        """,
                        (course_id, session_date, topic),
                    )
                    session_id = cursor.lastrowid

                return self._get_by_id_in_connection(connection, session_id)
        except sqlite3.IntegrityError as error:
            raise _attendance_session_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Attendance session could not be created.") from error

    def get_by_id(self, session_id: int) -> AttendanceSession | None:
        """Return an attendance session by primary key, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                return self._get_optional_by_id_in_connection(connection, session_id)
        except sqlite3.Error as error:
            raise DatabaseError("Attendance session could not be retrieved.") from error

    def get_by_course_date_topic(
        self,
        course_id: int,
        session_date: str,
        topic: str,
    ) -> AttendanceSession | None:
        """Return one session for the unique course/date/topic combination."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT {ATTENDANCE_SESSION_COLUMNS}
                    FROM attendance_sessions
                    WHERE course_id = ?
                      AND session_date = ?
                      AND topic = ?
                    """,
                    (course_id, session_date, topic),
                ).fetchone()

            return _attendance_session_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Attendance session could not be retrieved.") from error

    def list_sessions(
        self,
        course_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        topic_search: str | None = None,
    ) -> list[AttendanceSession]:
        """Return attendance sessions with optional filters."""
        where_parts: list[str] = []
        parameters: list[int | str] = []

        if course_id is not None:
            where_parts.append("s.course_id = ?")
            parameters.append(course_id)
        if date_from is not None:
            where_parts.append("s.session_date >= ?")
            parameters.append(date_from)
        if date_to is not None:
            where_parts.append("s.session_date <= ?")
            parameters.append(date_to)
        if topic_search is not None:
            where_parts.append("s.topic LIKE ? ESCAPE '\\'")
            parameters.append(_like_pattern(topic_search))

        where_clause = ""
        if where_parts:
            where_clause = f"WHERE {' AND '.join(where_parts)}"

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        s.session_id,
                        s.course_id,
                        s.session_date,
                        s.topic,
                        s.created_at
                    FROM attendance_sessions s
                    JOIN courses c ON c.course_id = s.course_id
                    {where_clause}
                    ORDER BY {ATTENDANCE_SESSION_ORDER_BY}
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_attendance_session_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Attendance sessions could not be listed.") from error

    def list_for_course(
        self,
        course_id: int,
        date_from: str | None = None,
        date_to: str | None = None,
        topic_search: str | None = None,
    ) -> list[AttendanceSession]:
        """Return attendance sessions for one course."""
        return self.list_sessions(
            course_id=course_id,
            date_from=date_from,
            date_to=date_to,
            topic_search=topic_search,
        )

    def _get_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        session_id: int,
    ) -> AttendanceSession:
        session = self._get_optional_by_id_in_connection(connection, session_id)
        if session is None:
            raise DatabaseError("Created attendance session could not be retrieved.")

        return session

    def _get_optional_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        session_id: int,
    ) -> AttendanceSession | None:
        row = connection.execute(
            f"""
            SELECT {ATTENDANCE_SESSION_COLUMNS}
            FROM attendance_sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        return _attendance_session_from_row(row) if row is not None else None


def _attendance_session_from_row(row) -> AttendanceSession:
    return AttendanceSession(
        session_id=row["session_id"],
        course_id=row["course_id"],
        session_date=row["session_date"],
        topic=row["topic"],
        created_at=row["created_at"],
    )


def _attendance_session_constraint_error(error: sqlite3.IntegrityError):
    message = str(error)
    if "attendance_sessions.course_id, attendance_sessions.session_date, attendance_sessions.topic" in message:
        return DuplicateRecordError(
            "Attendance session already exists for this course, date, and topic."
        )
    if "FOREIGN KEY constraint failed" in message:
        return RecordNotFoundError(
            "Course was not found for this attendance session operation."
        )

    return DatabaseError("Attendance session data violated a database constraint.")


def _like_pattern(search_text: str) -> str:
    escaped = (
        search_text.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"
