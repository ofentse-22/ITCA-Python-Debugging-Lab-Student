"""Integration tests for course enrolment service behavior."""

import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.course import (
    COURSE_ACTIVE_STATUS,
    COURSE_PLANNED_STATUS,
)
from itca_training_centre.models.course_enrolment import (
    ENROLMENT_ACTIVE_STATUS,
    ENROLMENT_CANCELLED_STATUS,
)
from itca_training_centre.services.course_enrolment_service import CourseEnrolmentService
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from tests.helpers import temporary_database_path


class CourseEnrolmentServiceTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.student_service = StudentService(self.database_path)
        self.course_service = CourseService(self.database_path)
        self.service = CourseEnrolmentService(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def _create_student(self, student_number="STU-1001", first_name="Amina", last_name="Nkosi"):
        return self.student_service.register_student(
            student_number,
            first_name,
            last_name,
        )

    def _create_course(self, course_code="PYF101", status=COURSE_ACTIVE_STATUS):
        return self.course_service.create_course(
            course_code,
            f"{course_code} Course",
            fee_amount="0",
            status=status,
        )

    def test_active_student_can_be_enrolled_in_active_course(self):
        student = self._create_student()
        course = self._create_course()

        enrolment = self.service.enrol_student(
            student_number=" stu-1001 ",
            course_code=" pyf101 ",
            enrolment_date="2026-09-01",
        )

        self.assertEqual(student.student_id, enrolment.student_id)
        self.assertEqual(course.course_id, enrolment.course_id)
        self.assertEqual("2026-09-01", enrolment.enrolment_date)
        self.assertEqual(ENROLMENT_ACTIVE_STATUS, enrolment.status)

    def test_missing_student_or_course_is_reported(self):
        self._create_student()
        self._create_course()

        with self.assertRaisesRegex(RecordNotFoundError, "No student"):
            self.service.enrol_student("STU-9999", "PYF101", "2026-09-01")
        with self.assertRaisesRegex(RecordNotFoundError, "No course"):
            self.service.enrol_student("STU-1001", "MISSING", "2026-09-01")

    def test_student_and_course_must_be_active_for_new_enrolments(self):
        self._create_student()
        self._create_course()
        self.student_service.deactivate_student("STU-1001")

        with self.assertRaisesRegex(ValidationError, "Student must be active"):
            self.service.enrol_student("STU-1001", "PYF101", "2026-09-01")

        self._create_student("STU-1002", "Bongi", "Mokoena")
        self._create_course("SQL101", status=COURSE_PLANNED_STATUS)

        with self.assertRaisesRegex(ValidationError, "Course must be active"):
            self.service.enrol_student("STU-1002", "SQL101", "2026-09-01")

    def test_duplicate_active_enrolment_is_rejected(self):
        self._create_student()
        self._create_course()
        self.service.enrol_student("STU-1001", "PYF101", "2026-09-01")

        with self.assertRaisesRegex(DuplicateRecordError, "actively enrolled"):
            self.service.enrol_student("STU-1001", "PYF101", "2026-09-02")

    def test_listing_filters_by_student_course_and_status(self):
        self._create_student("STU-1001", "Amina", "Nkosi")
        self._create_student("STU-1002", "Bongi", "Mokoena")
        self._create_course("PYF101")
        self._create_course("SQL101")
        first = self.service.enrol_student("STU-1001", "SQL101", "2026-09-03")
        second = self.service.enrol_student("STU-1002", "PYF101", "2026-09-02")
        third = self.service.enrol_student("STU-1001", "PYF101", "2026-09-01")

        self.assertEqual(
            [second.enrolment_id, third.enrolment_id, first.enrolment_id],
            [item.enrolment_id for item in self.service.list_enrolments()],
        )
        self.assertEqual(
            [third.enrolment_id, first.enrolment_id],
            [item.enrolment_id for item in self.service.list_student_enrolments("STU-1001")],
        )
        self.assertEqual(
            [second.enrolment_id, third.enrolment_id],
            [item.enrolment_id for item in self.service.list_course_enrolments("PYF101")],
        )
        self.assertEqual(
            [third.enrolment_id],
            [
                item.enrolment_id
                for item in self.service.list_filtered_enrolments(
                    student_number="STU-1001",
                    course_code="PYF101",
                    status=ENROLMENT_ACTIVE_STATUS,
                )
            ],
        )

    def test_cancel_preserves_history_and_allows_later_active_enrolment(self):
        self._create_student()
        self._create_course()
        original = self.service.enrol_student("STU-1001", "PYF101", "2026-09-01")

        cancelled = self.service.cancel_enrolment(
            "STU-1001",
            "PYF101",
            "2026-09-15",
            " Student withdrew ",
        )
        new_active = self.service.enrol_student("STU-1001", "PYF101", "2026-10-01")

        self.assertEqual(original.enrolment_id, cancelled.enrolment_id)
        self.assertEqual(ENROLMENT_CANCELLED_STATUS, cancelled.status)
        self.assertEqual("Student withdrew", cancelled.cancellation_reason)
        self.assertNotEqual(original.enrolment_id, new_active.enrolment_id)
        self.assertEqual(
            [new_active.enrolment_id],
            [item.enrolment_id for item in self.service.list_student_enrolments("STU-1001")],
        )
        self.assertEqual(
            [original.enrolment_id, new_active.enrolment_id],
            [
                item.enrolment_id
                for item in self.service.list_student_enrolments(
                    "STU-1001",
                    include_historical=True,
                )
            ],
        )

    def test_cancel_without_active_enrolment_reports_not_found(self):
        self._create_student()
        self._create_course()

        with self.assertRaisesRegex(RecordNotFoundError, "No active enrolment"):
            self.service.cancel_enrolment(
                "STU-1001",
                "PYF101",
                "2026-09-15",
                "Student withdrew",
            )

    def test_invalid_dates_reason_and_status_are_rejected(self):
        self._create_student()
        self._create_course()

        with self.assertRaisesRegex(ValidationError, "Enrolment date"):
            self.service.enrol_student("STU-1001", "PYF101", "09/01/2026")
        self.service.enrol_student("STU-1001", "PYF101", "2026-09-01")
        with self.assertRaisesRegex(ValidationError, "before enrolment date"):
            self.service.cancel_enrolment(
                "STU-1001",
                "PYF101",
                "2026-08-31",
                "Impossible date",
            )
        with self.assertRaisesRegex(ValidationError, "Cancellation date"):
            self.service.cancel_enrolment(
                "STU-1001",
                "PYF101",
                "2026/09/15",
                "Student withdrew",
            )
        with self.assertRaisesRegex(ValidationError, "Cancellation reason"):
            self.service.cancel_enrolment("STU-1001", "PYF101", "2026-09-15", "")
        with self.assertRaisesRegex(ValidationError, "Enrolment status"):
            self.service.list_enrolments(status="paused")

        active = self.service.list_student_enrolments("STU-1001")
        self.assertEqual([ENROLMENT_ACTIVE_STATUS], [item.status for item in active])


if __name__ == "__main__":
    unittest.main()
