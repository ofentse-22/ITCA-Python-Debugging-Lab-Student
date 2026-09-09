"""Tests for the AttendanceSession domain model."""

import unittest

from itca_training_centre.models.attendance_session import AttendanceSession


class AttendanceSessionModelTests(unittest.TestCase):
    def test_session_exposes_topic_state(self):
        session = AttendanceSession(
            session_id=1,
            course_id=10,
            session_date="2026-09-01",
            topic="Control Flow",
            created_at="2026-01-01T00:00:00.000Z",
        )

        self.assertTrue(session.has_topic)

    def test_blank_topic_is_allowed_by_the_schema(self):
        session = AttendanceSession(
            session_id=1,
            course_id=10,
            session_date="2026-09-01",
            topic="",
            created_at="2026-01-01T00:00:00.000Z",
        )

        self.assertFalse(session.has_topic)


if __name__ == "__main__":
    unittest.main()
