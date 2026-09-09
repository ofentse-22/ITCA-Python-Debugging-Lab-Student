"""Unit tests for assessment model behavior."""

from decimal import Decimal
import unittest

from itca_training_centre.models.assessment import (
    ASSESSMENT_ACTIVE_STATUS,
    ASSESSMENT_ARCHIVED_STATUS,
    Assessment,
)


class AssessmentModelTests(unittest.TestCase):
    def test_assessment_properties_reflect_status_and_target(self):
        assessment = Assessment(
            assessment_id=1,
            course_id=10,
            module_id=20,
            assessment_name="Variables Practical",
            assessment_type="practical",
            max_mark=Decimal("75.50"),
            weight=Decimal("10"),
            pass_mark=Decimal("50"),
            status=ASSESSMENT_ACTIVE_STATUS,
            created_at="2026-09-01T08:00:00.000Z",
            updated_at="2026-09-01T08:00:00.000Z",
        )

        self.assertTrue(assessment.is_active)
        self.assertFalse(assessment.is_archived)
        self.assertTrue(assessment.is_module_specific)
        self.assertFalse(assessment.is_course_level)

    def test_course_level_archived_assessment_properties(self):
        assessment = Assessment(
            assessment_id=1,
            course_id=10,
            module_id=None,
            assessment_name="Final Exam",
            assessment_type="exam",
            max_mark=Decimal("100"),
            weight=None,
            pass_mark=None,
            status=ASSESSMENT_ARCHIVED_STATUS,
            created_at="2026-09-01T08:00:00.000Z",
            updated_at="2026-09-01T08:00:00.000Z",
        )

        self.assertFalse(assessment.is_active)
        self.assertTrue(assessment.is_archived)
        self.assertFalse(assessment.is_module_specific)
        self.assertTrue(assessment.is_course_level)


if __name__ == "__main__":
    unittest.main()
