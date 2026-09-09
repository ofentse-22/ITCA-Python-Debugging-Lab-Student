"""Integration tests for student service business behavior."""

import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.student import ACTIVE_STATUS, INACTIVE_STATUS
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from tests.helpers import temporary_database_path


class StudentServiceTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.service = StudentService(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_valid_registration_normalizes_whitespace_and_email(self):
        student = self.service.register_student(
            student_number=" stu-1001 ",
            first_name="  Amina  ",
            last_name="  Nkosi  ",
            email=" AMINA.NKOSI@EXAMPLE.EDU ",
            phone=" 555-0101 ",
        )

        self.assertEqual("STU-1001", student.student_number)
        self.assertEqual("Amina", student.first_name)
        self.assertEqual("Nkosi", student.last_name)
        self.assertEqual("amina.nkosi@example.edu", student.email)
        self.assertEqual("555-0101", student.phone)

    def test_blank_required_fields_are_rejected(self):
        cases = [
            {"student_number": "", "first_name": "Amina", "last_name": "Nkosi"},
            {"student_number": "STU-1001", "first_name": " ", "last_name": "Nkosi"},
            {"student_number": "STU-1001", "first_name": "Amina", "last_name": ""},
        ]

        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValidationError):
                    self.service.register_student(**kwargs)

    def test_invalid_email_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.service.register_student(
                "STU-1001",
                "Amina",
                "Nkosi",
                "not-an-email",
                None,
            )

    def test_duplicate_identifier_is_translated(self):
        self.service.register_student("STU-1001", "Amina", "Nkosi")

        with self.assertRaisesRegex(DuplicateRecordError, "Student number"):
            self.service.register_student("stu-1001", "Bongi", "Mokoena")

    def test_get_missing_student_raises_not_found(self):
        with self.assertRaisesRegex(RecordNotFoundError, "STU-9999"):
            self.service.get_student_by_number("stu-9999")

    def test_update_student_changes_mutable_fields(self):
        self.service.register_student("STU-1001", "Amina", "Nkosi")

        updated = self.service.update_student(
            student_number="STU-1001",
            first_name="Amira",
            last_name="Naidoo",
            email="amira@example.edu",
            phone="555-0202",
        )

        self.assertEqual("STU-1001", updated.student_number)
        self.assertEqual("Amira", updated.first_name)
        self.assertEqual("Naidoo", updated.last_name)
        self.assertEqual("amira@example.edu", updated.email)
        self.assertEqual("555-0202", updated.phone)

    def test_invalid_update_is_rejected(self):
        self.service.register_student("STU-1001", "Amina", "Nkosi")

        with self.assertRaises(ValidationError):
            self.service.update_student(
                student_number="STU-1001",
                first_name="",
                last_name="Nkosi",
            )

    def test_deactivate_missing_student_raises_not_found(self):
        with self.assertRaises(RecordNotFoundError):
            self.service.deactivate_student("STU-9999")

    def test_repeated_deactivate_is_safe_and_keeps_inactive_status(self):
        registered = self.service.register_student("STU-1001", "Amina", "Nkosi")

        first_result = self.service.deactivate_student("STU-1001")
        second_result = self.service.deactivate_student("STU-1001")

        self.assertEqual(registered.student_id, first_result.student_id)
        self.assertEqual(registered.student_id, second_result.student_id)
        self.assertEqual(INACTIVE_STATUS, first_result.status)
        self.assertEqual(INACTIVE_STATUS, second_result.status)

    def test_reactivate_uses_same_record(self):
        registered = self.service.register_student("STU-1001", "Amina", "Nkosi")
        self.service.deactivate_student("STU-1001")

        reactivated = self.service.reactivate_student("STU-1001")

        self.assertEqual(registered.student_id, reactivated.student_id)
        self.assertEqual(ACTIVE_STATUS, reactivated.status)

    def test_search_normalizes_query(self):
        self.service.register_student("STU-1001", "Amina", "Nkosi")

        results = self.service.search_students("  amina  ")

        self.assertEqual(["STU-1001"], [student.student_number for student in results])

    def test_search_treats_punctuation_and_like_wildcards_as_data(self):
        self.service.register_student("STU-SAFE", "A'va", "Percent%;--_")
        self.service.register_student("STU-PLAIN", "Plain", "Student")

        percent_results = self.service.search_students("%", include_inactive=True)
        underscore_results = self.service.search_students("_", include_inactive=True)
        apostrophe_results = self.service.search_students("A'va", include_inactive=True)

        self.assertEqual(["STU-SAFE"], [student.student_number for student in percent_results])
        self.assertEqual(["STU-SAFE"], [student.student_number for student in underscore_results])
        self.assertEqual(["STU-SAFE"], [student.student_number for student in apostrophe_results])

    def test_active_listing_excludes_inactive_students(self):
        self.service.register_student("STU-1001", "Amina", "Nkosi")
        self.service.register_student("STU-1002", "Bongi", "Mokoena")
        self.service.deactivate_student("STU-1002")

        active_students = self.service.list_students()
        all_students = self.service.list_students(include_inactive=True)

        self.assertEqual(["STU-1001"], [student.student_number for student in active_students])
        self.assertEqual(
            ["STU-1002", "STU-1001"],
            [student.student_number for student in all_students],
        )

    def test_reactivation_does_not_create_duplicate_rows(self):
        registered = self.service.register_student("STU-1001", "Amina", "Nkosi")
        self.service.deactivate_student("STU-1001")
        self.service.reactivate_student("STU-1001")

        with open_database(self.database_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM students").fetchone()[0]

        self.assertEqual(1, count)
        self.assertEqual(registered.student_id, self.service.get_student_by_number("STU-1001").student_id)


if __name__ == "__main__":
    unittest.main()
