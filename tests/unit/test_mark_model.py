"""Unit tests for mark and result model structures."""

from decimal import Decimal
import unittest

from itca_training_centre.models.assessment import Assessment
from itca_training_centre.models.mark import (
    RESULT_PASS_STATE,
    AssessmentResult,
    AssessmentSummary,
    Mark,
    MarkCaptureEntry,
)


class MarkModelTests(unittest.TestCase):
    def test_mark_capture_entry_preserves_zero_as_real_input(self):
        entry = MarkCaptureEntry("STU-1001", Decimal("0"), "Started but not completed")

        self.assertEqual("STU-1001", entry.student_number)
        self.assertEqual(Decimal("0"), entry.mark_obtained)
        self.assertEqual("Started but not completed", entry.notes)

    def test_assessment_result_tracks_optional_pass_fail_state(self):
        assessment = Assessment(
            assessment_id=1,
            course_id=10,
            module_id=None,
            assessment_name="Final Exam",
            assessment_type="exam",
            max_mark=Decimal("100"),
            weight=None,
            pass_mark=Decimal("50"),
            status="active",
            created_at="2026-09-01T08:00:00.000Z",
            updated_at="2026-09-01T08:00:00.000Z",
        )
        mark = Mark(
            mark_id=2,
            assessment_id=1,
            student_id=3,
            mark_obtained=Decimal("75"),
            captured_at="2026-09-01T09:00:00.000Z",
            notes=None,
        )

        result = AssessmentResult(
            mark=mark,
            assessment=assessment,
            percentage=Decimal("75"),
            result_state=RESULT_PASS_STATE,
        )

        self.assertTrue(result.has_result_state)

    def test_assessment_summary_properties_handle_missing_pass_rule(self):
        summary = AssessmentSummary(
            assessment_id=1,
            recorded_count=0,
            average_mark=None,
            average_percentage=None,
            highest_mark=None,
            lowest_mark=None,
            pass_count=None,
            fail_count=None,
            pass_rate=None,
        )

        self.assertFalse(summary.has_results)
        self.assertFalse(summary.has_pass_fail_counts)


if __name__ == "__main__":
    unittest.main()
