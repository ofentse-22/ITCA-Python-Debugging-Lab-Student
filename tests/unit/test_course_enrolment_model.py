"""Tests for the CourseEnrolment domain model."""

import unittest

from itca_training_centre.models.course_enrolment import (
    ENROLMENT_ACTIVE_STATUS,
    ENROLMENT_CANCELLED_STATUS,
    ENROLMENT_COMPLETED_STATUS,
    ENROLMENT_STATUSES,
    CourseEnrolment,
)


class CourseEnrolmentModelTests(unittest.TestCase):
    def test_active_enrolment_state(self):
        enrolment = CourseEnrolment(
            enrolment_id=1,
            student_id=10,
            course_id=20,
            enrolment_date="2026-09-01",
            status=ENROLMENT_ACTIVE_STATUS,
            cancelled_at=None,
            cancellation_reason=None,
            created_at="2026-01-01T00:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
        )

        self.assertTrue(enrolment.is_active)
        self.assertFalse(enrolment.is_cancelled)
        self.assertFalse(enrolment.is_historical)

    def test_cancelled_and_completed_enrolments_are_historical(self):
        for status in (ENROLMENT_CANCELLED_STATUS, ENROLMENT_COMPLETED_STATUS):
            with self.subTest(status=status):
                enrolment = CourseEnrolment(
                    enrolment_id=1,
                    student_id=10,
                    course_id=20,
                    enrolment_date="2026-09-01",
                    status=status,
                    cancelled_at="2026-09-02" if status == ENROLMENT_CANCELLED_STATUS else None,
                    cancellation_reason="Student withdrew"
                    if status == ENROLMENT_CANCELLED_STATUS
                    else None,
                    created_at="2026-01-01T00:00:00.000Z",
                    updated_at="2026-01-01T00:00:00.000Z",
                )

                self.assertFalse(enrolment.is_active)
                self.assertTrue(enrolment.is_historical)

    def test_status_constants_match_schema_values(self):
        self.assertEqual(("active", "completed", "cancelled"), ENROLMENT_STATUSES)
        self.assertEqual("active", ENROLMENT_ACTIVE_STATUS)
        self.assertEqual("completed", ENROLMENT_COMPLETED_STATUS)
        self.assertEqual("cancelled", ENROLMENT_CANCELLED_STATUS)


if __name__ == "__main__":
    unittest.main()
