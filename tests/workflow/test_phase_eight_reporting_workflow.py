"""End-to-end Phase 8 reporting and statistics workflow tests."""

from decimal import Decimal
import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.services.assessment_service import (
    AssessmentService,
    round_percentage_for_display,
)
from itca_training_centre.services.attendance_service import AttendanceService
from itca_training_centre.services.report_service import ReportService
from tests.helpers import temporary_database_path
from tests.reporting_helpers import operational_table_counts, seed_reporting_data


class PhaseEightReportingWorkflowTests(unittest.TestCase):
    def test_reporting_workflow_uses_existing_truth_and_does_not_mutate(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)
            fixture = seed_reporting_data(database_path)
            reports = ReportService(database_path)
            attendance = AttendanceService(database_path)
            assessments = AssessmentService(database_path)

            attendance_truth = attendance.calculate_student_attendance(
                "STU-1001",
                "PYF101",
            )
            assessment_truth = assessments.list_assessment_results(
                fixture.assessment_practical.assessment_id
            )

            system = reports.get_system_overview()
            student = reports.get_student_progress("STU-1001")
            course = reports.get_course_overview("PYF101")
            course_attendance = reports.get_course_attendance_report("PYF101")
            low_attendance = reports.get_low_attendance_students("PYF101", "80")
            performance = reports.get_assessment_performance(
                fixture.assessment_practical.assessment_id
            )
            trainer = reports.get_trainer_assignment_report("TRN-1001")

            before = operational_table_counts(database_path)
            reports.get_system_overview()
            reports.get_student_progress("STU-1002")
            reports.get_course_overview("PYF101")
            reports.get_course_attendance_report("PYF101")
            reports.get_low_attendance_students("PYF101", "80")
            reports.get_assessment_performance(fixture.assessment_quiz.assessment_id)
            reports.get_trainer_assignment_report("TRN-1002")
            after = operational_table_counts(database_path)

        truth_by_student_id = {
            result.mark.student_id: result
            for result in assessment_truth
        }
        student_practical = next(
            row
            for row in student.assessment_results
            if row.assessment.assessment_name == "Variables Practical"
        )
        performance_rows = {
            row.student.student_number: row
            for row in performance.students
        }

        self.assertEqual(6, system.student_count)
        self.assertEqual(5, system.mark_count)
        self.assertEqual(
            attendance_truth.attendance_percentage,
            student.course_attendance[0].summary.attendance_percentage,
        )
        self.assertEqual(
            attendance_truth.attendance_percentage,
            student.overall_attendance.attendance_percentage,
        )
        self.assertEqual(Decimal("0"), student_practical.mark_obtained)
        self.assertEqual(Decimal("0"), student_practical.percentage)
        self.assertEqual("fail", student_practical.result_state)
        self.assertTrue(performance_rows["STU-1003"].is_missing)
        self.assertEqual(
            truth_by_student_id[fixture.student_bongi.student_id].percentage,
            performance_rows["STU-1002"].percentage,
        )
        self.assertEqual(
            Decimal("75.50"),
            round_percentage_for_display(performance_rows["STU-1002"].percentage),
        )
        self.assertEqual(50.0, course.attendance_summary.attendance_percentage)
        self.assertEqual(2, len(course_attendance.sessions))
        self.assertEqual(
            ["STU-1001", "STU-1002"],
            sorted(
                row.student.student_number
                for row in low_attendance.students_below_threshold
            ),
        )
        self.assertEqual(
            ["STU-1003"],
            [
                row.student.student_number
                for row in low_attendance.students_without_calculable_attendance
            ],
        )
        self.assertEqual(["PYF101", "SQL101"], [row.course_code for row in trainer.active_assignments])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
