"""Integration tests for initial schema constraints."""

from decimal import Decimal
import sqlite3
import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.decimal_storage import (
    decimal_from_storage,
    decimal_to_storage,
)
from itca_training_centre.data.migrations import initialize_database
from tests.helpers import temporary_database_path


class SchemaConstraintTests(unittest.TestCase):
    def test_student_number_is_unique(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                _insert_student(connection, "STU-1001")

                with self.assertRaises(sqlite3.IntegrityError):
                    _insert_student(connection, "STU-1001")

    def test_course_code_is_unique(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                _insert_course(connection, "PYF101")

                with self.assertRaises(sqlite3.IntegrityError):
                    _insert_course(connection, "PYF101")

    def test_invalid_foreign_key_is_rejected(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO modules (
                            course_id, module_code, module_name, sequence_number
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (999, "MOD-1", "Missing Course", 1),
                    )

    def test_valid_relationships_succeed(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                student_id = _insert_student(connection, "STU-1001")
                course_id = _insert_course(connection, "PYF101")
                module_id = _insert_module(connection, course_id, "PYF-M1", 1)
                assessment_id = _insert_assessment(connection, course_id, module_id)

                connection.execute(
                    """
                    INSERT INTO course_enrolments (
                        student_id, course_id, enrolment_date
                    )
                    VALUES (?, ?, ?)
                    """,
                    (student_id, course_id, "2026-01-10"),
                )
                connection.execute(
                    """
                    INSERT INTO marks (assessment_id, student_id, mark_obtained)
                    VALUES (?, ?, ?)
                    """,
                    (assessment_id, student_id, decimal_to_storage(Decimal("75.50"))),
                )

                mark = connection.execute(
                    "SELECT mark_obtained FROM marks WHERE student_id = ?",
                    (student_id,),
                ).fetchone()

            self.assertEqual(Decimal("75.50"), decimal_from_storage(mark["mark_obtained"]))

    def test_duplicate_active_enrolment_is_rejected(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                student_id = _insert_student(connection, "STU-1001")
                course_id = _insert_course(connection, "PYF101")
                _insert_enrolment(connection, student_id, course_id, "active")

                with self.assertRaises(sqlite3.IntegrityError):
                    _insert_enrolment(connection, student_id, course_id, "active")

    def test_cancelled_enrolment_does_not_block_new_active_enrolment(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                student_id = _insert_student(connection, "STU-1001")
                course_id = _insert_course(connection, "PYF101")
                _insert_enrolment(connection, student_id, course_id, "cancelled")
                _insert_enrolment(connection, student_id, course_id, "active")

                count = connection.execute(
                    "SELECT COUNT(*) FROM course_enrolments"
                ).fetchone()[0]

            self.assertEqual(2, count)

    def test_duplicate_attendance_record_is_rejected(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                student_id = _insert_student(connection, "STU-1001")
                course_id = _insert_course(connection, "PYF101")
                session_id = _insert_attendance_session(connection, course_id)

                _insert_attendance_record(connection, session_id, student_id)

                with self.assertRaises(sqlite3.IntegrityError):
                    _insert_attendance_record(connection, session_id, student_id)

    def test_duplicate_mark_for_student_assessment_is_rejected(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                student_id = _insert_student(connection, "STU-1001")
                course_id = _insert_course(connection, "PYF101")
                assessment_id = _insert_assessment(connection, course_id)

                _insert_mark(connection, assessment_id, student_id, "75.50")

                with self.assertRaises(sqlite3.IntegrityError):
                    _insert_mark(connection, assessment_id, student_id, "80")

    def test_restrict_delete_preserves_historical_relationships(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                student_id = _insert_student(connection, "STU-1001")
                course_id = _insert_course(connection, "PYF101")
                _insert_enrolment(connection, student_id, course_id, "active")

                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "DELETE FROM students WHERE student_id = ?",
                        (student_id,),
                    )

    def test_status_check_constraint_rejects_invalid_value(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO students (
                            student_number, first_name, last_name, status
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        ("STU-1001", "Amina", "Nkosi", "paused"),
                    )


def _insert_student(connection, student_number):
    cursor = connection.execute(
        """
        INSERT INTO students (student_number, first_name, last_name)
        VALUES (?, ?, ?)
        """,
        (student_number, "Amina", "Nkosi"),
    )
    return cursor.lastrowid


def _insert_course(connection, course_code):
    cursor = connection.execute(
        """
        INSERT INTO courses (course_code, course_name)
        VALUES (?, ?)
        """,
        (course_code, "Python Fundamentals"),
    )
    return cursor.lastrowid


def _insert_module(connection, course_id, module_code, sequence_number):
    cursor = connection.execute(
        """
        INSERT INTO modules (
            course_id, module_code, module_name, sequence_number
        )
        VALUES (?, ?, ?, ?)
        """,
        (course_id, module_code, "Variables and Data Types", sequence_number),
    )
    return cursor.lastrowid


def _insert_assessment(connection, course_id, module_id=None):
    cursor = connection.execute(
        """
        INSERT INTO assessments (
            course_id, module_id, assessment_name, assessment_type, max_mark
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            course_id,
            module_id,
            "Practical 1",
            "practical",
            decimal_to_storage(Decimal("100")),
        ),
    )
    return cursor.lastrowid


def _insert_enrolment(connection, student_id, course_id, status):
    cursor = connection.execute(
        """
        INSERT INTO course_enrolments (
            student_id, course_id, enrolment_date, status
        )
        VALUES (?, ?, ?, ?)
        """,
        (student_id, course_id, "2026-01-10", status),
    )
    return cursor.lastrowid


def _insert_attendance_session(connection, course_id):
    cursor = connection.execute(
        """
        INSERT INTO attendance_sessions (course_id, session_date, topic)
        VALUES (?, ?, ?)
        """,
        (course_id, "2026-01-11", "Control Flow"),
    )
    return cursor.lastrowid


def _insert_attendance_record(connection, session_id, student_id):
    cursor = connection.execute(
        """
        INSERT INTO attendance_records (session_id, student_id, status)
        VALUES (?, ?, ?)
        """,
        (session_id, student_id, "present"),
    )
    return cursor.lastrowid


def _insert_mark(connection, assessment_id, student_id, mark_obtained):
    cursor = connection.execute(
        """
        INSERT INTO marks (assessment_id, student_id, mark_obtained)
        VALUES (?, ?, ?)
        """,
        (assessment_id, student_id, mark_obtained),
    )
    return cursor.lastrowid


if __name__ == "__main__":
    unittest.main()
