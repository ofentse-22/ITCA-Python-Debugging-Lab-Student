"""Persistence operations for assessment marks."""

from decimal import Decimal
from pathlib import Path
import sqlite3

from ..data.connection import open_database, transaction
from ..data.decimal_storage import decimal_from_storage, decimal_to_storage
from ..models.mark import Mark
from ..utils.exceptions import DatabaseError, DuplicateRecordError, RecordNotFoundError


MARK_COLUMNS = """
mark_id,
assessment_id,
student_id,
mark_obtained,
captured_at,
notes
"""


class MarkRepository:
    """SQLite-backed repository for marks."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def create(
        self,
        assessment_id: int,
        student_id: int,
        mark_obtained: Decimal,
        notes: str | None = None,
    ) -> Mark:
        """Insert and return a new mark."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        INSERT INTO marks (
                            assessment_id,
                            student_id,
                            mark_obtained,
                            notes
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            assessment_id,
                            student_id,
                            decimal_to_storage(mark_obtained),
                            notes,
                        ),
                    )
                    mark_id = cursor.lastrowid

                return self._get_by_id_in_connection(connection, mark_id)
        except sqlite3.IntegrityError as error:
            raise _mark_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Mark could not be created.") from error
        except (TypeError, ValueError) as error:
            raise DatabaseError("Mark Decimal value could not be stored.") from error

    def create_many(
        self,
        marks: list[tuple[int, int, Decimal, str | None]],
    ) -> list[Mark]:
        """Insert class marks atomically and return created rows."""
        if not marks:
            return []

        try:
            with open_database(self.database_path) as connection:
                mark_ids = []
                with transaction(connection):
                    for assessment_id, student_id, mark_obtained, notes in marks:
                        cursor = connection.execute(
                            """
                            INSERT INTO marks (
                                assessment_id,
                                student_id,
                                mark_obtained,
                                notes
                            )
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                assessment_id,
                                student_id,
                                decimal_to_storage(mark_obtained),
                                notes,
                            ),
                        )
                        mark_ids.append(cursor.lastrowid)
                        connection.commit()

                return [
                    self._get_by_id_in_connection(connection, mark_id)
                    for mark_id in mark_ids
                ]
        except sqlite3.IntegrityError as error:
            raise _mark_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Class marks could not be created.") from error
        except (TypeError, ValueError) as error:
            raise DatabaseError("Mark Decimal value could not be stored.") from error

    def get_by_id(self, mark_id: int) -> Mark | None:
        """Return a mark by primary key, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                return self._get_optional_by_id_in_connection(connection, mark_id)
        except sqlite3.Error as error:
            raise DatabaseError("Mark could not be retrieved.") from error

    def get_for_student_assessment(
        self,
        assessment_id: int,
        student_id: int,
    ) -> Mark | None:
        """Return the authoritative mark for one student and assessment."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT {MARK_COLUMNS}
                    FROM marks
                    WHERE assessment_id = ?
                      AND student_id = ?
                    """,
                    (assessment_id, student_id),
                ).fetchone()

            return _mark_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Mark could not be retrieved.") from error

    def list_for_assessment(self, assessment_id: int) -> list[Mark]:
        """Return assessment results ordered by student name."""
        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        m.mark_id,
                        m.assessment_id,
                        m.student_id,
                        m.mark_obtained,
                        m.captured_at,
                        m.notes
                    FROM marks m
                    JOIN students s ON s.student_id = m.student_id
                    WHERE m.assessment_id = ?
                    ORDER BY lower(s.last_name), lower(s.first_name),
                             lower(s.student_number), m.mark_id
                    """,
                    (assessment_id,),
                ).fetchall()

            return [_mark_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Assessment marks could not be listed.") from error

    def list_for_student(
        self,
        student_id: int,
        course_id: int | None = None,
    ) -> list[Mark]:
        """Return one student's result history in deterministic context order."""
        where_parts = ["m.student_id = ?"]
        parameters: list[int] = [student_id]

        if course_id is not None:
            where_parts.append("a.course_id = ?")
            parameters.append(course_id)

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        m.mark_id,
                        m.assessment_id,
                        m.student_id,
                        m.mark_obtained,
                        m.captured_at,
                        m.notes
                    FROM marks m
                    JOIN assessments a ON a.assessment_id = m.assessment_id
                    JOIN courses c ON c.course_id = a.course_id
                    LEFT JOIN modules module ON module.module_id = a.module_id
                    WHERE {' AND '.join(where_parts)}
                    ORDER BY lower(c.course_code),
                             CASE WHEN a.module_id IS NULL THEN 0 ELSE 1 END,
                             COALESCE(module.sequence_number, 0),
                             lower(COALESCE(module.module_code, '')),
                             lower(a.assessment_name),
                             a.assessment_id,
                             m.mark_id
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_mark_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Student marks could not be listed.") from error

    def update(
        self,
        mark_id: int,
        mark_obtained: Decimal,
        notes: str | None,
    ) -> Mark | None:
        """Correct a mark while preserving row identity."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE marks
                        SET mark_obtained = ?,
                            notes = ?
                        WHERE mark_id = ?
                        """,
                        (
                            decimal_to_storage(mark_obtained),
                            notes,
                            mark_id,
                        ),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, mark_id)
        except sqlite3.IntegrityError as error:
            raise _mark_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Mark could not be updated.") from error
        except (TypeError, ValueError) as error:
            raise DatabaseError("Mark Decimal value could not be stored.") from error

    def _get_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        mark_id: int,
    ) -> Mark:
        mark = self._get_optional_by_id_in_connection(connection, mark_id)
        if mark is None:
            raise DatabaseError("Created mark could not be retrieved.")

        return mark

    def _get_optional_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        mark_id: int,
    ) -> Mark | None:
        row = connection.execute(
            f"""
            SELECT {MARK_COLUMNS}
            FROM marks
            WHERE mark_id = ?
            """,
            (mark_id,),
        ).fetchone()
        return _mark_from_row(row) if row is not None else None


def _mark_from_row(row) -> Mark:
    return Mark(
        mark_id=row["mark_id"],
        assessment_id=row["assessment_id"],
        student_id=row["student_id"],
        mark_obtained=decimal_from_storage(row["mark_obtained"]),
        captured_at=row["captured_at"],
        notes=row["notes"],
    )


def _mark_constraint_error(error: sqlite3.IntegrityError):
    message = str(error)
    if "marks.assessment_id, marks.student_id" in message:
        return DuplicateRecordError(
            "Result is already recorded for this student and assessment."
        )
    if "FOREIGN KEY constraint failed" in message:
        return RecordNotFoundError(
            "Assessment or student was not found for this mark operation."
        )

    return DatabaseError("Mark data violated a database constraint.")
