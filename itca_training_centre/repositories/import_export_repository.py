"""Database helpers for confirmed imports and operational exports."""

from pathlib import Path
import sqlite3

from ..data.connection import open_database, transaction
from ..data.decimal_storage import decimal_to_storage
from ..models.course import COURSE_ACTIVE_STATUS
from ..models.import_export import (
    CourseImportRow,
    EnrolmentImportRow,
    ModuleImportRow,
    StudentImportRow,
    TrainerImportRow,
)
from ..models.student import ACTIVE_STATUS
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)


class ImportExportRepository:
    """SQLite-backed persistence helpers for import/export services."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def get_student_context(self, student_number: str) -> tuple[int, str] | None:
        """Return a student ID/status tuple for a stable student number."""
        return self._get_context("students", "student_id", "student_number", student_number)

    def get_course_context(self, course_code: str) -> tuple[int, str] | None:
        """Return a course ID/status tuple for a stable course code."""
        return self._get_context("courses", "course_id", "course_code", course_code)

    def get_trainer_context(self, trainer_number: str) -> tuple[int, str] | None:
        """Return a trainer ID/status tuple for a stable trainer number."""
        return self._get_context("trainers", "trainer_id", "trainer_number", trainer_number)

    def student_email_exists(self, email: str | None) -> bool:
        """Return True when an imported student email already belongs to a row."""
        return self._email_exists("students", email)

    def trainer_email_exists(self, email: str | None) -> bool:
        """Return True when an imported trainer email already belongs to a row."""
        return self._email_exists("trainers", email)

    def module_exists(self, course_code: str, module_code: str) -> bool:
        """Return True when a course already contains a module code."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM modules m
                    JOIN courses c ON c.course_id = m.course_id
                    WHERE c.course_code = ?
                      AND m.module_code = ?
                    LIMIT 1
                    """,
                    (course_code, module_code),
                ).fetchone()
                return row is not None
        except sqlite3.Error as error:
            raise DatabaseError("Module conflict check failed.") from error

    def module_sequence_exists(self, course_code: str, sequence_number: int) -> bool:
        """Return True when a course already contains a module sequence number."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM modules m
                    JOIN courses c ON c.course_id = m.course_id
                    WHERE c.course_code = ?
                      AND m.sequence_number = ?
                    LIMIT 1
                    """,
                    (course_code, sequence_number),
                ).fetchone()
                return row is not None
        except sqlite3.Error as error:
            raise DatabaseError("Module conflict check failed.") from error

    def active_enrolment_exists(self, student_number: str, course_code: str) -> bool:
        """Return True when a student is already actively enrolled in a course."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM course_enrolments e
                    JOIN students s ON s.student_id = e.student_id
                    JOIN courses c ON c.course_id = e.course_id
                    WHERE s.student_number = ?
                      AND c.course_code = ?
                      AND e.status = 'active'
                    LIMIT 1
                    """,
                    (student_number, course_code),
                ).fetchone()
                return row is not None
        except sqlite3.Error as error:
            raise DatabaseError("Enrolment conflict check failed.") from error

    def create_students(self, rows: tuple[StudentImportRow, ...]) -> int:
        """Create validated student rows in one transaction."""
        if not rows:
            return 0

        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    for row in rows:
                        connection.execute(
                            """
                            INSERT INTO students (
                                student_number,
                                first_name,
                                last_name,
                                email,
                                phone,
                                status
                            )
                            VALUES (?, ?, ?, ?, ?, 'active')
                            """,
                            (
                                row.student_number,
                                row.first_name,
                                row.last_name,
                                row.email,
                                row.phone,
                            ),
                        )
                return len(rows)
        except sqlite3.IntegrityError as error:
            raise _import_integrity_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Student import could not be committed.") from error

    def create_courses(self, rows: tuple[CourseImportRow, ...]) -> int:
        """Create validated course rows in one transaction."""
        if not rows:
            return 0

        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    for row in rows:
                        connection.execute(
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
                                row.course_code,
                                row.course_name,
                                row.description,
                                decimal_to_storage(row.fee_amount),
                                row.status,
                            ),
                        )
                return len(rows)
        except sqlite3.IntegrityError as error:
            raise _import_integrity_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Course import could not be committed.") from error
        except (TypeError, ValueError) as error:
            raise DatabaseError("Course fee amount could not be stored.") from error

    def create_modules(self, rows: tuple[ModuleImportRow, ...]) -> int:
        """Create validated module rows in one transaction."""
        if not rows:
            return 0

        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    for row in rows:
                        course_id = _get_required_course_id(connection, row.course_code)
                        connection.execute(
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
                                course_id,
                                row.module_code,
                                row.module_name,
                                row.sequence_number,
                                row.status,
                            ),
                        )
                return len(rows)
        except sqlite3.IntegrityError as error:
            raise _import_integrity_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Module import could not be committed.") from error

    def create_trainers(self, rows: tuple[TrainerImportRow, ...]) -> int:
        """Create validated trainer rows in one transaction."""
        if not rows:
            return 0

        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    for row in rows:
                        connection.execute(
                            """
                            INSERT INTO trainers (
                                trainer_number,
                                first_name,
                                last_name,
                                email,
                                phone,
                                status
                            )
                            VALUES (?, ?, ?, ?, ?, 'active')
                            """,
                            (
                                row.trainer_number,
                                row.first_name,
                                row.last_name,
                                row.email,
                                row.phone,
                            ),
                        )
                return len(rows)
        except sqlite3.IntegrityError as error:
            raise _import_integrity_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Trainer import could not be committed.") from error

    def create_enrolments(self, rows: tuple[EnrolmentImportRow, ...]) -> int:
        """Create validated active enrolment rows in one transaction."""
        if not rows:
            return 0

        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    for row in rows:
                        student_id = _get_active_student_id(connection, row.student_number)
                        course_id = _get_active_course_id(connection, row.course_code)
                        _reject_existing_active_enrolment(
                            connection,
                            student_id,
                            course_id,
                        )
                        connection.execute(
                            """
                            INSERT INTO course_enrolments (
                                student_id,
                                course_id,
                                enrolment_date,
                                status
                            )
                            VALUES (?, ?, ?, 'active')
                            """,
                            (student_id, course_id, row.enrolment_date),
                        )
                return len(rows)
        except sqlite3.IntegrityError as error:
            raise _import_integrity_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Enrolment import could not be committed.") from error

    def list_student_export_rows(self) -> list[dict[str, object]]:
        """Return student export rows in deterministic business-key order."""
        return self._list_rows(
            """
            SELECT
                student_number,
                first_name,
                last_name,
                email,
                phone,
                status
            FROM students
            ORDER BY lower(last_name), lower(first_name), lower(student_number)
            """
        )

    def list_course_export_rows(self) -> list[dict[str, object]]:
        """Return course export rows in deterministic business-key order."""
        return self._list_rows(
            """
            SELECT
                course_code,
                course_name,
                description,
                fee_amount,
                status
            FROM courses
            ORDER BY lower(course_code)
            """
        )

    def list_module_export_rows(self) -> list[dict[str, object]]:
        """Return course-module export rows in deterministic business-key order."""
        return self._list_rows(
            """
            SELECT
                c.course_code,
                m.module_code,
                m.module_name,
                m.sequence_number,
                m.status
            FROM modules m
            JOIN courses c ON c.course_id = m.course_id
            ORDER BY lower(c.course_code), m.sequence_number, lower(m.module_code)
            """
        )

    def list_trainer_export_rows(self) -> list[dict[str, object]]:
        """Return trainer export rows in deterministic business-key order."""
        return self._list_rows(
            """
            SELECT
                trainer_number,
                first_name,
                last_name,
                email,
                phone,
                status
            FROM trainers
            ORDER BY lower(last_name), lower(first_name), lower(trainer_number)
            """
        )

    def list_enrolment_export_rows(self) -> list[dict[str, object]]:
        """Return enrolment export rows using student and course business keys."""
        return self._list_rows(
            """
            SELECT
                s.student_number,
                c.course_code,
                e.enrolment_date,
                e.status,
                e.cancelled_at,
                e.cancellation_reason
            FROM course_enrolments e
            JOIN students s ON s.student_id = e.student_id
            JOIN courses c ON c.course_id = e.course_id
            ORDER BY lower(c.course_code), lower(s.last_name), lower(s.first_name),
                     lower(s.student_number), e.enrolment_date, e.enrolment_id
            """
        )

    def list_trainer_assignment_export_rows(self) -> list[dict[str, object]]:
        """Return trainer-assignment exports using business keys."""
        return self._list_rows(
            """
            SELECT
                t.trainer_number,
                c.course_code,
                a.assigned_from,
                a.assigned_to,
                a.status
            FROM trainer_assignments a
            JOIN trainers t ON t.trainer_id = a.trainer_id
            JOIN courses c ON c.course_id = a.course_id
            ORDER BY lower(c.course_code), lower(t.last_name), lower(t.first_name),
                     lower(t.trainer_number), a.assigned_from, a.assignment_id
            """
        )

    def list_attendance_export_rows(self) -> list[dict[str, object]]:
        """Return attendance record exports using business keys."""
        return self._list_rows(
            """
            SELECT
                c.course_code,
                sessions.session_date,
                sessions.topic,
                s.student_number,
                records.status,
                records.notes
            FROM attendance_records records
            JOIN attendance_sessions sessions ON sessions.session_id = records.session_id
            JOIN courses c ON c.course_id = sessions.course_id
            JOIN students s ON s.student_id = records.student_id
            ORDER BY lower(c.course_code), sessions.session_date,
                     lower(s.last_name), lower(s.first_name),
                     lower(s.student_number), records.attendance_record_id
            """
        )

    def list_assessment_export_rows(self) -> list[dict[str, object]]:
        """Return assessment definition exports with business context."""
        return self._list_rows(
            """
            SELECT
                a.assessment_id,
                c.course_code,
                COALESCE(m.module_code, '') AS module_code,
                a.assessment_name,
                a.assessment_type,
                a.max_mark,
                a.weight,
                a.pass_mark,
                a.status
            FROM assessments a
            JOIN courses c ON c.course_id = a.course_id
            LEFT JOIN modules m ON m.module_id = a.module_id
            ORDER BY lower(c.course_code),
                     CASE WHEN a.module_id IS NULL THEN 0 ELSE 1 END,
                     COALESCE(m.sequence_number, 0),
                     lower(COALESCE(m.module_code, '')),
                     lower(a.assessment_name),
                     a.assessment_id
            """
        )

    def list_mark_export_rows(self) -> list[dict[str, object]]:
        """Return mark exports with assessment and student business context."""
        return self._list_rows(
            """
            SELECT
                a.assessment_id,
                c.course_code,
                COALESCE(module.module_code, '') AS module_code,
                a.assessment_name,
                a.assessment_type,
                s.student_number,
                ROUND(
                    (CAST(m.mark_obtained AS REAL) / CAST(a.max_mark AS REAL)) * 100,
                    2
                ) AS mark_obtained,
                m.captured_at,
                m.notes
            FROM marks m
            JOIN assessments a ON a.assessment_id = m.assessment_id
            JOIN courses c ON c.course_id = a.course_id
            LEFT JOIN modules module ON module.module_id = a.module_id
            JOIN students s ON s.student_id = m.student_id
            ORDER BY lower(c.course_code),
                     CASE WHEN a.module_id IS NULL THEN 0 ELSE 1 END,
                     COALESCE(module.sequence_number, 0),
                     lower(COALESCE(module.module_code, '')),
                     lower(a.assessment_name),
                     a.assessment_id,
                     lower(s.last_name),
                     lower(s.first_name),
                     lower(s.student_number),
                     m.mark_id
            """
        )

    def count_table_rows(self, table_name: str) -> int:
        """Return a table count for read-only verification tests."""
        if table_name not in {
            "students",
            "courses",
            "modules",
            "trainers",
            "course_enrolments",
            "trainer_assignments",
            "attendance_sessions",
            "attendance_records",
            "assessments",
            "marks",
        }:
            raise ValueError(f"Unsupported table name: {table_name}")

        try:
            with open_database(self.database_path) as connection:
                return connection.execute(
                    f"SELECT COUNT(*) FROM {table_name}"
                ).fetchone()[0]
        except sqlite3.Error as error:
            raise DatabaseError("Table row count could not be read.") from error

    def _get_context(
        self,
        table_name: str,
        id_column: str,
        key_column: str,
        key_value: str,
    ) -> tuple[int, str] | None:
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT {id_column} AS entity_id, status
                    FROM {table_name}
                    WHERE {key_column} = ?
                    """,
                    (key_value,),
                ).fetchone()
                if row is None:
                    return None
                return row["entity_id"], row["status"]
        except sqlite3.Error as error:
            raise DatabaseError("Import conflict check failed.") from error

    def _email_exists(self, table_name: str, email: str | None) -> bool:
        if email is None:
            return False

        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT 1
                    FROM {table_name}
                    WHERE email = ?
                    LIMIT 1
                    """,
                    (email,),
                ).fetchone()
                return row is not None
        except sqlite3.Error as error:
            raise DatabaseError("Email conflict check failed.") from error

    def _list_rows(self, statement: str) -> list[dict[str, object]]:
        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(statement).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Export rows could not be read.") from error


def _get_required_course_id(connection: sqlite3.Connection, course_code: str) -> int:
    row = connection.execute(
        "SELECT course_id FROM courses WHERE course_code = ?",
        (course_code,),
    ).fetchone()
    if row is None:
        raise RecordNotFoundError(f"No course was found for code {course_code}.")

    return row["course_id"]


def _get_active_student_id(connection: sqlite3.Connection, student_number: str) -> int:
    row = connection.execute(
        "SELECT student_id, status FROM students WHERE student_number = ?",
        (student_number,),
    ).fetchone()
    if row is None:
        raise RecordNotFoundError(f"No student was found for number {student_number}.")
    if row["status"] != ACTIVE_STATUS:
        raise ValidationError("Student must be active before enrolling in a course.")

    return row["student_id"]


def _get_active_course_id(connection: sqlite3.Connection, course_code: str) -> int:
    row = connection.execute(
        "SELECT course_id, status FROM courses WHERE course_code = ?",
        (course_code,),
    ).fetchone()
    if row is None:
        raise RecordNotFoundError(f"No course was found for code {course_code}.")
    if row["status"] != COURSE_ACTIVE_STATUS:
        raise ValidationError("Course must be active before enrolling students.")

    return row["course_id"]


def _reject_existing_active_enrolment(
    connection: sqlite3.Connection,
    student_id: int,
    course_id: int,
) -> None:
    row = connection.execute(
        """
        SELECT 1
        FROM course_enrolments
        WHERE student_id = ?
          AND course_id = ?
          AND status = 'active'
        LIMIT 1
        """,
        (student_id, course_id),
    ).fetchone()
    if row is not None:
        raise DuplicateRecordError("Student is already actively enrolled in this course.")


def _import_integrity_error(error: sqlite3.IntegrityError):
    message = str(error)
    if "students.student_number" in message:
        return DuplicateRecordError("Student number already exists.")
    if "students.email" in message:
        return DuplicateRecordError("Email address already exists.")
    if "courses.course_code" in message:
        return DuplicateRecordError("Course code already exists.")
    if "modules.course_id, modules.module_code" in message:
        return DuplicateRecordError("Module code already exists for this course.")
    if "modules.course_id, modules.sequence_number" in message:
        return DuplicateRecordError("Module sequence already exists for this course.")
    if "trainers.trainer_number" in message:
        return DuplicateRecordError("Trainer number already exists.")
    if "trainers.email" in message:
        return DuplicateRecordError("Email address already exists.")
    if "course_enrolments.student_id, course_enrolments.course_id" in message:
        return DuplicateRecordError("Student is already actively enrolled in this course.")
    if "FOREIGN KEY constraint failed" in message:
        return RecordNotFoundError("Imported relationship data refers to a missing row.")

    return DatabaseError("Imported data violated a database constraint.")
