"""Unit tests for report read models."""

from decimal import Decimal
import unittest

from itca_training_centre.models.reports import (
    AssessmentPerformanceStudentRow,
    AttendanceStatusSummary,
    ReportAssessment,
    ReportStudent,
    StudentAssessmentReportRow,
)


class ReportModelTests(unittest.TestCase):
    def _assessment(self, pass_mark=Decimal("50")):
        return ReportAssessment(
            assessment_id=1,
            course_id=1,
            course_code="PYF101",
            course_name="Python Fundamentals",
            course_status="active",
            module_id=None,
            module_code=None,
            module_name=None,
            module_status=None,
            assessment_name="Course Quiz",
            assessment_type="quiz",
            max_mark=Decimal("100"),
            weight=None,
            pass_mark=pass_mark,
            status="active",
        )

    def _student(self):
        return ReportStudent(
            student_id=1,
            student_number="STU-1001",
            first_name="Amina",
            last_name="Nkosi",
            status="active",
        )

    def test_report_identity_models_expose_display_names(self):
        student = self._student()

        self.assertEqual("Amina Nkosi", student.full_name)

    def test_attendance_summary_keeps_no_calculable_percentage_distinct(self):
        summary = AttendanceStatusSummary(
            session_count=2,
            record_count=2,
            present_count=0,
            late_count=0,
            absent_count=0,
            excused_count=1,
            unknown_count=1,
            percentage_denominator=0,
            attendance_percentage=None,
        )

        self.assertEqual(0, summary.attended_count)
        self.assertTrue(summary.has_records)
        self.assertFalse(summary.has_percentage)

    def test_student_assessment_row_distinguishes_zero_missing_and_unclassified(self):
        zero = StudentAssessmentReportRow(
            assessment=self._assessment(),
            mark_id=1,
            mark_obtained=Decimal("0"),
            percentage=Decimal("0"),
            result_state="fail",
            captured_at="2026-09-01T00:00:00Z",
            notes=None,
        )
        missing = StudentAssessmentReportRow(
            assessment=self._assessment(),
            mark_id=None,
            mark_obtained=None,
            percentage=None,
            result_state=None,
            captured_at=None,
            notes=None,
        )
        unclassified = StudentAssessmentReportRow(
            assessment=self._assessment(pass_mark=None),
            mark_id=2,
            mark_obtained=Decimal("7"),
            percentage=Decimal("70"),
            result_state=None,
            captured_at="2026-09-01T00:00:00Z",
            notes=None,
        )

        self.assertTrue(zero.has_mark)
        self.assertFalse(zero.is_missing)
        self.assertEqual(Decimal("0"), zero.mark_obtained)
        self.assertFalse(missing.has_mark)
        self.assertTrue(missing.is_missing)
        self.assertTrue(unclassified.has_mark)
        self.assertTrue(unclassified.is_unclassified)

    def test_assessment_performance_row_distinguishes_history(self):
        historical = AssessmentPerformanceStudentRow(
            student=self._student(),
            mark_id=1,
            mark_obtained=Decimal("40"),
            percentage=Decimal("40"),
            result_state="fail",
            captured_at="2026-09-01T00:00:00Z",
            notes=None,
            is_currently_eligible=False,
        )

        self.assertTrue(historical.has_mark)
        self.assertFalse(historical.is_currently_eligible)


if __name__ == "__main__":
    unittest.main()
