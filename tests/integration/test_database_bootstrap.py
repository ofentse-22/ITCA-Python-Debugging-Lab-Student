"""Integration tests for database initialization and schema completeness."""

import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import (
    get_schema_version,
    initialize_database,
)
from itca_training_centre.data.schema import LATEST_SCHEMA_VERSION
from tests.helpers import temporary_database_path


EXPECTED_TABLES = {
    "schema_migrations",
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
}

EXPECTED_INDEXES = {
    "idx_students_name",
    "idx_students_status",
    "idx_courses_status",
    "idx_modules_course_id",
    "idx_modules_status",
    "idx_trainers_name",
    "idx_trainers_status",
    "idx_course_enrolments_student_id",
    "idx_course_enrolments_course_id",
    "idx_course_enrolments_status",
    "uq_course_enrolments_active_student_course",
    "idx_trainer_assignments_trainer_id",
    "idx_trainer_assignments_course_id",
    "idx_trainer_assignments_status",
    "uq_trainer_assignments_active_trainer_course",
    "idx_attendance_sessions_course_date",
    "idx_attendance_records_student_id",
    "idx_assessments_course_id",
    "idx_assessments_module_id",
    "idx_assessments_status",
    "idx_marks_student_id",
}


class DatabaseBootstrapTests(unittest.TestCase):
    def test_fresh_database_initializes_successfully(self):
        with temporary_database_path() as database_path:
            status = initialize_database(database_path)

            self.assertTrue(database_path.exists())
            self.assertEqual(database_path, status.database_path)
            self.assertEqual(LATEST_SCHEMA_VERSION, status.current_version)
            self.assertEqual((1,), status.applied_migrations)

    def test_expected_schema_exists(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                tables = _table_names(connection)
                indexes = _index_names(connection)

            self.assertTrue(EXPECTED_TABLES.issubset(tables))
            self.assertTrue(EXPECTED_INDEXES.issubset(indexes))

    def test_schema_version_record_exists(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                row = connection.execute(
                    """
                    SELECT version, name, applied_at
                    FROM schema_migrations
                    WHERE version = ?
                    """,
                    (1,),
                ).fetchone()

            self.assertEqual(1, row["version"])
            self.assertEqual("initial_training_centre_schema", row["name"])
            self.assertTrue(row["applied_at"].endswith("Z"))

    def test_initialization_is_idempotent_and_preserves_existing_data(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO students (student_number, first_name, last_name)
                    VALUES (?, ?, ?)
                    """,
                    ("STU-1001", "Amina", "Nkosi"),
                )

            second_status = initialize_database(database_path)

            with open_database(database_path) as connection:
                count = connection.execute("SELECT COUNT(*) FROM students").fetchone()[0]

            self.assertEqual(1, count)
            self.assertEqual((1,), second_status.applied_migrations)

    def test_schema_version_helper_returns_current_version(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                self.assertEqual(1, get_schema_version(connection))

    def test_test_database_path_stays_inside_temporary_directory(self):
        with temporary_database_path() as database_path:
            self.assertIn("test.sqlite3", database_path.name)
            self.assertFalse(str(database_path).endswith("itca_training_centre.sqlite3"))


def _table_names(connection):
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """
    ).fetchall()
    return {row["name"] for row in rows}


def _index_names(connection):
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'index'
          AND name NOT LIKE 'sqlite_autoindex_%'
        """
    ).fetchall()
    return {row["name"] for row in rows}


if __name__ == "__main__":
    unittest.main()
