"""Tests for the Course domain model."""

from decimal import Decimal
import unittest

from itca_training_centre.models.course import (
    COURSE_ACTIVE_STATUS,
    COURSE_ARCHIVED_STATUS,
    COURSE_COMPLETED_STATUS,
    COURSE_PLANNED_STATUS,
    COURSE_STATUSES,
    Course,
)


class CourseModelTests(unittest.TestCase):
    def test_course_exposes_active_and_archived_state(self):
        course = Course(
            course_id=1,
            course_code="PYF101",
            course_name="Python Fundamentals",
            description="Core Python skills",
            fee_amount=Decimal("1500.50"),
            status=COURSE_ACTIVE_STATUS,
            created_at="2026-01-01T00:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
        )

        self.assertTrue(course.is_active)
        self.assertFalse(course.is_archived)

    def test_archived_course_is_not_active(self):
        course = Course(
            course_id=1,
            course_code="PYF101",
            course_name="Python Fundamentals",
            description=None,
            fee_amount=Decimal("0"),
            status=COURSE_ARCHIVED_STATUS,
            created_at="2026-01-01T00:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
        )

        self.assertFalse(course.is_active)
        self.assertTrue(course.is_archived)

    def test_status_constants_match_schema_values(self):
        self.assertEqual(
            ("planned", "active", "completed", "archived"),
            COURSE_STATUSES,
        )
        self.assertEqual("planned", COURSE_PLANNED_STATUS)
        self.assertEqual("completed", COURSE_COMPLETED_STATUS)


if __name__ == "__main__":
    unittest.main()
