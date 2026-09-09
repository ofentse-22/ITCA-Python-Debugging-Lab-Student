"""Tests for the Student domain model."""

import unittest

from itca_training_centre.models.student import (
    ACTIVE_STATUS,
    ARCHIVED_STATUS,
    INACTIVE_STATUS,
    STUDENT_STATUSES,
    Student,
)


class StudentModelTests(unittest.TestCase):
    def test_student_exposes_display_name_and_active_state(self):
        student = Student(
            student_id=1,
            student_number="STU-1001",
            first_name="Amina",
            last_name="Nkosi",
            email="amina@example.edu",
            phone="555-0101",
            status=ACTIVE_STATUS,
            created_at="2026-01-01T00:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
            archived_at=None,
        )

        self.assertEqual("Amina Nkosi", student.full_name)
        self.assertTrue(student.is_active)
        self.assertFalse(student.is_inactive)

    def test_inactive_and_archived_students_are_not_active(self):
        for status in (INACTIVE_STATUS, ARCHIVED_STATUS):
            with self.subTest(status=status):
                student = Student(
                    student_id=1,
                    student_number="STU-1001",
                    first_name="Amina",
                    last_name="Nkosi",
                    email=None,
                    phone=None,
                    status=status,
                    created_at="2026-01-01T00:00:00.000Z",
                    updated_at="2026-01-01T00:00:00.000Z",
                    archived_at=None,
                )

                self.assertFalse(student.is_active)
                self.assertTrue(student.is_inactive)

    def test_status_constants_match_schema_values(self):
        self.assertEqual(("active", "inactive", "archived"), STUDENT_STATUSES)


if __name__ == "__main__":
    unittest.main()
