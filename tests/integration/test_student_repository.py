"""Integration tests for the student repository."""

import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.student import ACTIVE_STATUS, INACTIVE_STATUS
from itca_training_centre.repositories.student_repository import StudentRepository
from itca_training_centre.utils.exceptions import DuplicateRecordError
from tests.helpers import temporary_database_path


class StudentRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.repository = StudentRepository(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_create_student_round_trips_fields(self):
        student = self.repository.create(
            student_number="STU-1001",
            first_name="Amina",
            last_name="Nkosi",
            email="amina@example.edu",
            phone="555-0101",
        )

        self.assertIsInstance(student.student_id, int)
        self.assertEqual("STU-1001", student.student_number)
        self.assertEqual("Amina", student.first_name)
        self.assertEqual("Nkosi", student.last_name)
        self.assertEqual("amina@example.edu", student.email)
        self.assertEqual("555-0101", student.phone)
        self.assertEqual(ACTIVE_STATUS, student.status)
        self.assertTrue(student.created_at.endswith("Z"))
        self.assertTrue(student.updated_at.endswith("Z"))

    def test_get_existing_student_by_id_and_number(self):
        created = self.repository.create("STU-1001", "Amina", "Nkosi", None, None)

        by_id = self.repository.get_by_id(created.student_id)
        by_number = self.repository.get_by_student_number("STU-1001")

        self.assertEqual(created, by_id)
        self.assertEqual(created, by_number)

    def test_missing_student_returns_none(self):
        self.assertIsNone(self.repository.get_by_id(999))
        self.assertIsNone(self.repository.get_by_student_number("STU-9999"))

    def test_list_students_excludes_inactive_by_default(self):
        active = self.repository.create("STU-1001", "Amina", "Nkosi", None, None)
        inactive = self.repository.create("STU-1002", "Bongi", "Mokoena", None, None)
        self.repository.deactivate(inactive.student_id)

        students = self.repository.list_students()

        self.assertEqual([active.student_number], [student.student_number for student in students])

    def test_list_students_can_include_inactive(self):
        active = self.repository.create("STU-1001", "Amina", "Nkosi", None, None)
        inactive = self.repository.create("STU-1002", "Bongi", "Mokoena", None, None)
        self.repository.deactivate(inactive.student_id)

        students = self.repository.list_students(include_inactive=True)

        self.assertEqual(
            [inactive.student_number, active.student_number],
            [student.student_number for student in students],
        )
        self.assertEqual(INACTIVE_STATUS, students[0].status)

    def test_list_students_uses_deterministic_name_ordering(self):
        self.repository.create("STU-1003", "Zola", "Zulu", None, None)
        self.repository.create("STU-1001", "Amina", "Nkosi", None, None)
        self.repository.create("STU-1002", "Bongi", "Mokoena", None, None)

        students = self.repository.list_students()

        self.assertEqual(
            ["STU-1002", "STU-1001", "STU-1003"],
            [student.student_number for student in students],
        )

    def test_search_finds_identifier_name_combined_name_and_email(self):
        self.repository.create(
            "STU-1001",
            "Amina",
            "Nkosi",
            "amina.nkosi@example.edu",
            None,
        )

        terms = ["STU-1001", "Ami", "Nkosi", "Amina Nkosi", "example.edu"]
        for term in terms:
            with self.subTest(term=term):
                results = self.repository.search(term)
                self.assertEqual(["STU-1001"], [student.student_number for student in results])

    def test_search_excludes_inactive_unless_requested(self):
        inactive = self.repository.create("STU-1001", "Amina", "Nkosi", None, None)
        self.repository.deactivate(inactive.student_id)

        self.assertEqual([], self.repository.search("Amina"))
        self.assertEqual(
            ["STU-1001"],
            [student.student_number for student in self.repository.search("Amina", True)],
        )

    def test_search_returns_no_results_for_missing_text(self):
        self.repository.create("STU-1001", "Amina", "Nkosi", None, None)

        self.assertEqual([], self.repository.search("Missing"))

    def test_update_mutable_fields_preserves_identifier_and_status(self):
        student = self.repository.create("STU-1001", "Amina", "Nkosi", None, None)

        updated = self.repository.update(
            student_id=student.student_id,
            first_name="Amira",
            last_name="Naidoo",
            email="amira@example.edu",
            phone="555-0202",
        )

        self.assertEqual(student.student_id, updated.student_id)
        self.assertEqual("STU-1001", updated.student_number)
        self.assertEqual("Amira", updated.first_name)
        self.assertEqual("Naidoo", updated.last_name)
        self.assertEqual("amira@example.edu", updated.email)
        self.assertEqual("555-0202", updated.phone)
        self.assertEqual(ACTIVE_STATUS, updated.status)

    def test_update_missing_student_returns_none(self):
        result = self.repository.update(999, "Amina", "Nkosi", None, None)

        self.assertIsNone(result)

    def test_deactivate_and_reactivate_keep_same_physical_record(self):
        student = self.repository.create("STU-1001", "Amina", "Nkosi", None, None)

        inactive = self.repository.deactivate(student.student_id)
        active_again = self.repository.reactivate(student.student_id)

        with open_database(self.database_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM students").fetchone()[0]

        self.assertEqual(1, count)
        self.assertEqual(student.student_id, inactive.student_id)
        self.assertEqual(student.student_id, active_again.student_id)
        self.assertEqual(INACTIVE_STATUS, inactive.status)
        self.assertEqual(ACTIVE_STATUS, active_again.status)

    def test_duplicate_student_number_is_rejected(self):
        self.repository.create("STU-1001", "Amina", "Nkosi", None, None)

        with self.assertRaisesRegex(DuplicateRecordError, "Student number"):
            self.repository.create("STU-1001", "Bongi", "Mokoena", None, None)

    def test_duplicate_email_is_rejected(self):
        self.repository.create("STU-1001", "Amina", "Nkosi", "shared@example.edu", None)

        with self.assertRaisesRegex(DuplicateRecordError, "Email"):
            self.repository.create("STU-1002", "Bongi", "Mokoena", "shared@example.edu", None)


if __name__ == "__main__":
    unittest.main()
