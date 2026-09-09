"""Persistence operations for attendance records."""

from pathlib import Path
import sqlite3

from ..data.connection import open_database, transaction
from ..models.attendance_record import AttendanceRecord
from ..utils.exceptions import DatabaseError, DuplicateRecordError, RecordNotFoundError


ATTENDANCE_RECORD_COLUMNS = """
attendance_record_id,
session_id,
student_id,
status,
notes,
updated_at
"""


class AttendanceRecordRepository:
    """SQLite-backed repository for per-student attendance records."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def create(
        self,
        session_id: int,
        student_id: int,
        status: str,
        notes: str | None = None,
    ) -> AttendanceRecord:
        """Insert and return one attendance record."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        INSERT INTO attendance_records (
                            session_id,
                            student_id,
                            status,
                            notes
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (session_id, student_id, status, notes),
                    )
                    record_id = cursor.lastrowid

                return self._get_by_id_in_connection(connection, record_id)
        except sqlite3.IntegrityError as error:
            raise _attendance_record_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Attendance record could not be created.") from error

    def create_many(
        self,
        records: list[tuple[int, int, str, str | None]],
    ) -> list[AttendanceRecord]:
        """Insert a class register atomically and return created records."""
        if not records:
            return []

        try:
            with open_database(self.database_path) as connection:
                record_ids = []
                with transaction(connection):
                    for session_id, student_id, status, notes in records:
                        cursor = connection.execute(
                            """
                            INSERT INTO attendance_records (
                                session_id,
                                student_id,
                                status,
                                notes
                            )
                            VALUES (?, ?, ?, ?)
                            """,
                            (session_id, student_id, status, notes),
                        )
                        record_ids.append(cursor.lastrowid)

                return [
                    self._get_by_id_in_connection(connection, record_id)
                    for record_id in record_ids
                ]
        except sqlite3.IntegrityError as error:
            raise _attendance_record_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Attendance register could not be created.") from error

    def get_by_id(self, attendance_record_id: int) -> AttendanceRecord | None:
        """Return an attendance record by primary key, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                return self._get_optional_by_id_in_connection(
                    connection,
                    attendance_record_id,
                )
        except sqlite3.Error as error:
            raise DatabaseError("Attendance record could not be retrieved.") from error

    def get_for_student_session(
        self,
        session_id: int,
        student_id: int,
    ) -> AttendanceRecord | None:
        """Return one attendance record for a student/session pair."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT {ATTENDANCE_RECORD_COLUMNS}
                    FROM attendance_records
                    WHERE session_id = ?
                      AND student_id = ?
                    """,
                    (session_id, student_id),
                ).fetchone()

            return _attendance_record_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Attendance record could not be retrieved.") from error

    def list_for_session(self, session_id: int) -> list[AttendanceRecord]:
        """Return a session register in deterministic student order."""
        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        r.attendance_record_id,
                        r.session_id,
                        r.student_id,
                        r.status,
                        r.notes,
                        r.updated_at
                    FROM attendance_records r
                    JOIN students s ON s.student_id = r.student_id
                    WHERE r.session_id = ?
                    ORDER BY lower(s.last_name), lower(s.first_name),
                             lower(s.student_number), r.attendance_record_id
                    """,
                    (session_id,),
                ).fetchall()

            return [_attendance_record_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Attendance records could not be listed.") from error

    def list_for_student(
        self,
        student_id: int,
        course_id: int | None = None,
    ) -> list[AttendanceRecord]:
        """Return one student's attendance history."""
        where_parts = ["r.student_id = ?"]
        parameters: list[int] = [student_id]

        if course_id is not None:
            where_parts.append("session.course_id = ?")
            parameters.append(course_id)

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        r.attendance_record_id,
                        r.session_id,
                        r.student_id,
                        r.status,
                        r.notes,
                        r.updated_at
                    FROM attendance_records r
                    JOIN attendance_sessions session
                        ON session.session_id = r.session_id
                    JOIN courses c ON c.course_id = session.course_id
                    WHERE {' AND '.join(where_parts)}
                    ORDER BY session.session_date, lower(c.course_code),
                             session.session_id, r.attendance_record_id
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_attendance_record_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Attendance records could not be listed.") from error

    def update(
        self,
        attendance_record_id: int,
        status: str,
        notes: str | None,
    ) -> AttendanceRecord | None:
        """Update a record correction while preserving row identity."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE attendance_records
                        SET status = ?,
                            notes = ?,
                            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        WHERE attendance_record_id = ?
                        """,
                        (status, notes, attendance_record_id),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(
                    connection,
                    attendance_record_id,
                )
        except sqlite3.IntegrityError as error:
            raise _attendance_record_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Attendance record could not be updated.") from error

    def _get_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        attendance_record_id: int,
    ) -> AttendanceRecord:
        record = self._get_optional_by_id_in_connection(
            connection,
            attendance_record_id,
        )
        if record is None:
            raise DatabaseError("Created attendance record could not be retrieved.")

        return record

    def _get_optional_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        attendance_record_id: int,
    ) -> AttendanceRecord | None:
        row = connection.execute(
            f"""
            SELECT {ATTENDANCE_RECORD_COLUMNS}
            FROM attendance_records
            WHERE attendance_record_id = ?
            """,
            (attendance_record_id,),
        ).fetchone()
        return _attendance_record_from_row(row) if row is not None else None


def _attendance_record_from_row(row) -> AttendanceRecord:
    return AttendanceRecord(
        attendance_record_id=row["attendance_record_id"],
        session_id=row["session_id"],
        student_id=row["student_id"],
        status=row["status"],
        notes=row["notes"],
        updated_at=row["updated_at"],
    )


def _attendance_record_constraint_error(error: sqlite3.IntegrityError):
    message = str(error)
    if "attendance_records.session_id, attendance_records.student_id" in message:
        return DuplicateRecordError(
            "Attendance is already recorded for this student and session."
        )
    if "FOREIGN KEY constraint failed" in message:
        return RecordNotFoundError(
            "Session or student was not found for this attendance operation."
        )

    return DatabaseError("Attendance record data violated a database constraint.")
