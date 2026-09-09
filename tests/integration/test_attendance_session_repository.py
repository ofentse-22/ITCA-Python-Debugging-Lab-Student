"""Integration tests for the attendance session repository."""

from decimal import Decimal
import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.course import COURSE_ACTIVE_STATUS
from itca_training_centre.repositories.attendance_session_repository import (
    AttendanceSessionRepository,
)
from itca_training_centre.repositories.course_repository import CourseRepository
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
)
from tests.helpers import temporary_database_path


class AttendanceSessionRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.course_repository = CourseRepository(self.database_path)
        self.repository = AttendanceSessionRepository(self.database_path)
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

    def test_create_session_round_trips_fields(self):
        session = self.repository.create(
            course_id=self.course_a.course_id,
            session_date="2026-09-01",
            topic="Control Flow",
        )

        self.assertIsInstance(session.session_id, int)
        self.assertEqual(self.course_a.course_id, session.course_id)
        self.assertEqual("2026-09-01", session.session_date)
        self.assertEqual("Control Flow", session.topic)
        self.assertTrue(session.created_at.endswith("Z"))

    def test_get_existing_session_by_id_and_unique_combination(self):
        created = self.repository.create(
            self.course_a.course_id,
            "2026-09-01",
            "Control Flow",
        )

        by_id = self.repository.get_by_id(created.session_id)
        by_combination = self.repository.get_by_course_date_topic(
            self.course_a.course_id,
            "2026-09-01",
            "Control Flow",
        )

        self.assertEqual(created, by_id)
        self.assertEqual(created, by_combination)

    def test_missing_session_returns_none(self):
        self.assertIsNone(self.repository.get_by_id(999))
        self.assertIsNone(
            self.repository.get_by_course_date_topic(
                self.course_a.course_id,
                "2026-09-01",
                "Control Flow",
            )
        )

    def test_duplicate_course_date_topic_is_rejected(self):
        self.repository.create(self.course_a.course_id, "2026-09-01", "Control Flow")

        with self.assertRaisesRegex(DuplicateRecordError, "already exists"):
            self.repository.create(
                self.course_a.course_id,
                "2026-09-01",
                "Control Flow",
            )

    def test_same_date_can_be_used_for_different_topic_or_course(self):
        first = self.repository.create(
            self.course_a.course_id,
            "2026-09-01",
            "Control Flow",
        )
        second = self.repository.create(
            self.course_a.course_id,
            "2026-09-01",
            "Collections",
        )
        third = self.repository.create(
            self.course_b.course_id,
            "2026-09-01",
            "Control Flow",
        )

        self.assertNotEqual(first.session_id, second.session_id)
        self.assertNotEqual(first.session_id, third.session_id)

    def test_create_for_missing_course_is_translated(self):
        with self.assertRaisesRegex(RecordNotFoundError, "Course"):
            self.repository.create(999, "2026-09-01", "Control Flow")

    def test_list_sessions_filters_and_uses_deterministic_ordering(self):
        third = self.repository.create(
            self.course_b.course_id,
            "2026-09-02",
            "Relational Tables",
        )
        second = self.repository.create(
            self.course_a.course_id,
            "2026-09-01",
            "Loops",
        )
        first = self.repository.create(
            self.course_a.course_id,
            "2026-09-01",
            "Control Flow",
        )

        all_sessions = self.repository.list_sessions()
        course_sessions = self.repository.list_for_course(self.course_a.course_id)
        date_filtered = self.repository.list_sessions(date_from="2026-09-02")
        topic_filtered = self.repository.list_sessions(topic_search="flow")

        self.assertEqual(
            [first.session_id, second.session_id, third.session_id],
            [session.session_id for session in all_sessions],
        )
        self.assertEqual(
            [first.session_id, second.session_id],
            [session.session_id for session in course_sessions],
        )
        self.assertEqual([third.session_id], [session.session_id for session in date_filtered])
        self.assertEqual([first.session_id], [session.session_id for session in topic_filtered])


if __name__ == "__main__":
    unittest.main()
