"""Integration tests for the course enrolment repository."""

from decimal import Decimal
import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.course import COURSE_ACTIVE_STATUS
from itca_training_centre.models.course_enrolment import (
    ENROLMENT_ACTIVE_STATUS,
    ENROLMENT_CANCELLED_STATUS,
)
from itca_training_centre.repositories.course_enrolment_repository import (
    CourseEnrolmentRepository,
)
from itca_training_centre.repositories.course_repository import CourseRepository
from itca_training_centre.repositories.student_repository import StudentRepository
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
)
from tests.helpers import temporary_database_path


class CourseEnrolmentRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.student_repository = StudentRepository(self.database_path)
        self.course_repository = CourseRepository(self.database_path)
        self.repository = CourseEnrolmentRepository(self.database_path)
        self.student_a = self.student_repository.create(
            "STU-1001",
            "Amina",
            "Nkosi",
            None,
            None,
        )
        self.student_b = self.student_repository.create(
            "STU-1002",
            "Bongi",
            "Mokoena",
            None,
            None,
        )
        self.course_a = self.course_repository.create(
            "PYF101",
            "Python Fundamentals",
            None,
            Decimal("0"),
            COURSE_ACTIVE_STATUS,
        )
        self.course_b = self.course_repository.create(
            "SQL101",
            "SQLite Basics",
            None,
            Decimal("0"),
            COURSE_ACTIVE_STATUS,
        )

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_create_enrolment_round_trips_fields(self):
        enrolment = self.repository.create(
            self.student_a.student_id,
            self.course_a.course_id,
            "2026-09-01",
        )

        self.assertIsInstance(enrolment.enrolment_id, int)
        self.assertEqual(self.student_a.student_id, enrolment.student_id)
        self.assertEqual(self.course_a.course_id, enrolment.course_id)
        self.assertEqual("2026-09-01", enrolment.enrolment_date)
        self.assertEqual(ENROLMENT_ACTIVE_STATUS, enrolment.status)
        self.assertIsNone(enrolment.cancelled_at)
        self.assertIsNone(enrolment.cancellation_reason)
        self.assertTrue(enrolment.created_at.endswith("Z"))
        self.assertTrue(enrolment.updated_at.endswith("Z"))

    def test_get_existing_enrolment_by_id_and_active_pair(self):
        created = self.repository.create(
            self.student_a.student_id,
            self.course_a.course_id,
            "2026-09-01",
        )

        by_id = self.repository.get_by_id(created.enrolment_id)
        by_pair = self.repository.get_active_for_student_course(
            self.student_a.student_id,
            self.course_a.course_id,
        )

        self.assertEqual(created, by_id)
        self.assertEqual(created, by_pair)

    def test_missing_enrolment_returns_none(self):
        self.assertIsNone(self.repository.get_by_id(999))
        self.assertIsNone(
            self.repository.get_active_for_student_course(
                self.student_a.student_id,
                self.course_a.course_id,
            )
        )

    def test_list_methods_filter_and_order_relationships(self):
        first = self.repository.create(
            self.student_a.student_id,
            self.course_b.course_id,
            "2026-09-03",
        )
        second = self.repository.create(
            self.student_b.student_id,
            self.course_a.course_id,
            "2026-09-02",
        )
        third = self.repository.create(
            self.student_a.student_id,
            self.course_a.course_id,
            "2026-09-01",
        )

        all_enrolments = self.repository.list_enrolments()
        student_enrolments = self.repository.list_for_student(self.student_a.student_id)
        course_enrolments = self.repository.list_for_course(self.course_a.course_id)
        pair_enrolments = self.repository.list_for_student_course(
            self.student_a.student_id,
            self.course_a.course_id,
        )

        self.assertEqual(
            [second.enrolment_id, third.enrolment_id, first.enrolment_id],
            [enrolment.enrolment_id for enrolment in all_enrolments],
        )
        self.assertEqual(
            [third.enrolment_id, first.enrolment_id],
            [enrolment.enrolment_id for enrolment in student_enrolments],
        )
        self.assertEqual(
            [second.enrolment_id, third.enrolment_id],
            [enrolment.enrolment_id for enrolment in course_enrolments],
        )
        self.assertEqual([third.enrolment_id], [item.enrolment_id for item in pair_enrolments])

    def test_historical_enrolments_are_excluded_by_default(self):
        enrolment = self.repository.create(
            self.student_a.student_id,
            self.course_a.course_id,
            "2026-09-01",
        )
        cancelled = self.repository.cancel(
            enrolment.enrolment_id,
            "2026-09-15",
            "Student withdrew",
        )

        active_results = self.repository.list_for_student(self.student_a.student_id)
        historical_results = self.repository.list_for_student(
            self.student_a.student_id,
            include_historical=True,
        )

        self.assertEqual(ENROLMENT_CANCELLED_STATUS, cancelled.status)
        self.assertEqual([], active_results)
        self.assertEqual([enrolment.enrolment_id], [item.enrolment_id for item in historical_results])

    def test_duplicate_active_enrolment_is_rejected_but_new_active_after_cancel_is_allowed(self):
        original = self.repository.create(
            self.student_a.student_id,
            self.course_a.course_id,
            "2026-09-01",
        )

        with self.assertRaisesRegex(DuplicateRecordError, "actively enrolled"):
            self.repository.create(
                self.student_a.student_id,
                self.course_a.course_id,
                "2026-09-02",
            )

        self.repository.cancel(original.enrolment_id, "2026-09-15", "Student withdrew")
        new_active = self.repository.create(
            self.student_a.student_id,
            self.course_a.course_id,
            "2026-10-01",
        )

        self.assertNotEqual(original.enrolment_id, new_active.enrolment_id)
        self.assertEqual(
            new_active.enrolment_id,
            self.repository.get_active_for_student_course(
                self.student_a.student_id,
                self.course_a.course_id,
            ).enrolment_id,
        )

    def test_cancel_missing_enrolment_returns_none(self):
        self.assertIsNone(
            self.repository.cancel(999, "2026-09-15", "Student withdrew")
        )

    def test_create_for_missing_student_or_course_is_translated(self):
        with self.assertRaisesRegex(RecordNotFoundError, "Student or course"):
            self.repository.create(999, self.course_a.course_id, "2026-09-01")
        with self.assertRaisesRegex(RecordNotFoundError, "Student or course"):
            self.repository.create(self.student_a.student_id, 999, "2026-09-01")


if __name__ == "__main__":
    unittest.main()
