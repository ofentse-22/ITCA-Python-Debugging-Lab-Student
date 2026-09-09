"""Integration tests for the attendance record repository."""

from decimal import Decimal
import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.attendance_record import (
    ATTENDANCE_ABSENT_STATUS,
    ATTENDANCE_LATE_STATUS,
    ATTENDANCE_PRESENT_STATUS,
)
from itca_training_centre.models.course import COURSE_ACTIVE_STATUS
from itca_training_centre.repositories.attendance_record_repository import (
    AttendanceRecordRepository,
)
from itca_training_centre.repositories.attendance_session_repository import (
    AttendanceSessionRepository,
)
from itca_training_centre.repositories.course_repository import CourseRepository
from itca_training_centre.repositories.student_repository import StudentRepository
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
)
from tests.helpers import temporary_database_path


class AttendanceRecordRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.student_repository = StudentRepository(self.database_path)
        self.course_repository = CourseRepository(self.database_path)
        self.session_repository = AttendanceSessionRepository(self.database_path)
        self.repository = AttendanceRecordRepository(self.database_path)
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
        self.session_a = self.session_repository.create(
            self.course_a.course_id,
            "2026-09-01",
            "Control Flow",
        )
        self.session_b = self.session_repository.create(
            self.course_a.course_id,
            "2026-09-02",
            "Loops",
        )
        self.session_c = self.session_repository.create(
            self.course_b.course_id,
            "2026-09-01",
            "Tables",
        )

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_create_record_round_trips_fields(self):
        record = self.repository.create(
            self.session_a.session_id,
            self.student_a.student_id,
            ATTENDANCE_PRESENT_STATUS,
            "On time",
        )

        self.assertIsInstance(record.attendance_record_id, int)
        self.assertEqual(self.session_a.session_id, record.session_id)
        self.assertEqual(self.student_a.student_id, record.student_id)
        self.assertEqual(ATTENDANCE_PRESENT_STATUS, record.status)
        self.assertEqual("On time", record.notes)
        self.assertTrue(record.updated_at.endswith("Z"))

    def test_get_existing_record_by_id_and_student_session(self):
        created = self.repository.create(
            self.session_a.session_id,
            self.student_a.student_id,
            ATTENDANCE_PRESENT_STATUS,
        )

        by_id = self.repository.get_by_id(created.attendance_record_id)
        by_pair = self.repository.get_for_student_session(
            self.session_a.session_id,
            self.student_a.student_id,
        )

        self.assertEqual(created, by_id)
        self.assertEqual(created, by_pair)

    def test_missing_record_returns_none(self):
        self.assertIsNone(self.repository.get_by_id(999))
        self.assertIsNone(
            self.repository.get_for_student_session(
                self.session_a.session_id,
                self.student_a.student_id,
            )
        )

    def test_duplicate_student_session_record_is_rejected(self):
        self.repository.create(
            self.session_a.session_id,
            self.student_a.student_id,
            ATTENDANCE_PRESENT_STATUS,
        )

        with self.assertRaisesRegex(DuplicateRecordError, "already recorded"):
            self.repository.create(
                self.session_a.session_id,
                self.student_a.student_id,
                ATTENDANCE_ABSENT_STATUS,
            )

    def test_create_for_missing_session_or_student_is_translated(self):
        with self.assertRaisesRegex(RecordNotFoundError, "Session or student"):
            self.repository.create(999, self.student_a.student_id, ATTENDANCE_PRESENT_STATUS)
        with self.assertRaisesRegex(RecordNotFoundError, "Session or student"):
            self.repository.create(self.session_a.session_id, 999, ATTENDANCE_PRESENT_STATUS)

    def test_list_for_session_uses_student_name_ordering(self):
        second = self.repository.create(
            self.session_a.session_id,
            self.student_a.student_id,
            ATTENDANCE_PRESENT_STATUS,
        )
        first = self.repository.create(
            self.session_a.session_id,
            self.student_b.student_id,
            ATTENDANCE_ABSENT_STATUS,
        )

        records = self.repository.list_for_session(self.session_a.session_id)

        self.assertEqual(
            [first.attendance_record_id, second.attendance_record_id],
            [record.attendance_record_id for record in records],
        )

    def test_list_for_student_uses_session_date_and_course_ordering(self):
        third = self.repository.create(
            self.session_b.session_id,
            self.student_a.student_id,
            ATTENDANCE_ABSENT_STATUS,
        )
        second = self.repository.create(
            self.session_c.session_id,
            self.student_a.student_id,
            ATTENDANCE_LATE_STATUS,
        )
        first = self.repository.create(
            self.session_a.session_id,
            self.student_a.student_id,
            ATTENDANCE_PRESENT_STATUS,
        )

        all_records = self.repository.list_for_student(self.student_a.student_id)
        course_records = self.repository.list_for_student(
            self.student_a.student_id,
            course_id=self.course_a.course_id,
        )

        self.assertEqual(
            [first.attendance_record_id, second.attendance_record_id, third.attendance_record_id],
            [record.attendance_record_id for record in all_records],
        )
        self.assertEqual(
            [first.attendance_record_id, third.attendance_record_id],
            [record.attendance_record_id for record in course_records],
        )

    def test_update_status_and_notes_keeps_same_record_id(self):
        created = self.repository.create(
            self.session_a.session_id,
            self.student_a.student_id,
            ATTENDANCE_ABSENT_STATUS,
            "Sick",
        )

        updated = self.repository.update(
            created.attendance_record_id,
            ATTENDANCE_LATE_STATUS,
            "Arrived late",
        )

        self.assertEqual(created.attendance_record_id, updated.attendance_record_id)
        self.assertEqual(ATTENDANCE_LATE_STATUS, updated.status)
        self.assertEqual("Arrived late", updated.notes)

    def test_create_many_rolls_back_when_register_is_not_coherent(self):
        with self.assertRaisesRegex(DuplicateRecordError, "already recorded"):
            self.repository.create_many(
                [
                    (
                        self.session_a.session_id,
                        self.student_a.student_id,
                        ATTENDANCE_PRESENT_STATUS,
                        None,
                    ),
                    (
                        self.session_a.session_id,
                        self.student_a.student_id,
                        ATTENDANCE_ABSENT_STATUS,
                        None,
                    ),
                ]
            )

        self.assertEqual([], self.repository.list_for_session(self.session_a.session_id))


if __name__ == "__main__":
    unittest.main()
