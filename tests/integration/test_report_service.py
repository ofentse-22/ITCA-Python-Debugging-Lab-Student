"""Integration tests for report service business behavior."""

from decimal import Decimal
import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.services.assessment_service import (
    AssessmentService,
    round_percentage_for_display,
)
from itca_training_centre.services.course_enrolment_service import CourseEnrolmentService
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.report_service import ReportService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.services.trainer_service import TrainerService
from itca_training_centre.utils.exceptions import RecordNotFoundError, ValidationError
from tests.helpers import temporary_database_path
from tests.reporting_helpers import operational_table_counts, seed_reporting_data


class ReportServiceTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.service = ReportService(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_system_overview_reports_empty_and_populated_counts(self):
        empty = self.service.get_system_overview()
        self.assertEqual(0, empty.student_count)
        self.assertEqual(0, empty.mark_count)

        seed_reporting_data(self.database_path)
        populated = self.service.get_system_overview()

        self.assertEqual(6, populated.student_count)
        self.assertEqual(5, populated.active_student_count)
        self.assertEqual(1, populated.cancelled_enrolment_count)
        self.assertEqual(1, populated.ended_trainer_assignment_count)
        self.assertEqual(8, populated.attendance_record_count)
        self.assertEqual(5, populated.mark_count)

    def test_student_progress_handles_not_found_and_no_enrolments(self):
        seed_reporting_data(self.database_path)

        with self.assertRaisesRegex(RecordNotFoundError, "No student"):
            self.service.get_student_progress("STU-404")

        report = self.service.get_student_progress("STU-9999")

        self.assertEqual("STU-9999", report.student.student_number)
        self.assertEqual((), report.enrolments)
        self.assertEqual(0, report.overall_attendance.record_count)
        self.assertIsNone(report.overall_attendance.attendance_percentage)
        self.assertEqual((), report.course_attendance)
        self.assertEqual((), report.assessment_results)

    def test_student_progress_preserves_zero_missing_unclassified_and_history(self):
        fixture = seed_reporting_data(self.database_path)

        amina = self.service.get_student_progress(" stu-1001 ")
        celia = self.service.get_student_progress("STU-1003")
        esi = self.service.get_student_progress("STU-1005")

        self.assertEqual(50.0, amina.overall_attendance.attendance_percentage)
        self.assertEqual(50.0, amina.course_attendance[0].summary.attendance_percentage)
        self.assertEqual(
            ["Course Quiz", "Variables Practical"],
            [row.assessment.assessment_name for row in amina.assessment_results],
        )
        results_by_name = {
            row.assessment.assessment_name: row
            for row in amina.assessment_results
        }
        practical = results_by_name["Variables Practical"]
        quiz = results_by_name["Course Quiz"]
        self.assertEqual(fixture.assessment_practical.assessment_id, practical.assessment.assessment_id)
        self.assertEqual("archived", practical.assessment.status)
        self.assertEqual(Decimal("0"), practical.mark_obtained)
        self.assertEqual(Decimal("0"), practical.percentage)
        self.assertEqual("fail", practical.result_state)
        self.assertTrue(practical.has_mark)
        self.assertEqual((Decimal("1") / Decimal("3")) * Decimal("100"), quiz.percentage)
        self.assertIsNone(quiz.result_state)
        self.assertTrue(quiz.is_unclassified)

        self.assertTrue(all(row.is_missing for row in celia.assessment_results))
        self.assertEqual(["cancelled"], [row.status for row in esi.enrolments])
        self.assertEqual(1, len(esi.enrolments))
        self.assertEqual("inactive", esi.student.status)

    def test_course_overview_reports_modules_relationships_and_performance(self):
        fixture = seed_reporting_data(self.database_path)

        report = self.service.get_course_overview("PYF101")

        self.assertEqual(fixture.course_python.course_id, report.course.course_id)
        self.assertEqual(["MOD-101", "MOD-102"], [module.module_code for module in report.modules])
        self.assertEqual(["archived", "active"], [module.status for module in report.modules])
        self.assertEqual(3, report.active_enrolment_count)
        self.assertEqual(1, report.historical_enrolment_count)
        self.assertEqual(1, report.active_trainer_assignment_count)
        self.assertEqual(1, report.historical_trainer_assignment_count)
        self.assertEqual(2, report.attendance_summary.session_count)
        self.assertEqual(8, report.attendance_summary.record_count)
        self.assertEqual(50.0, report.attendance_summary.attendance_percentage)
        self.assertEqual(
            ["Course Quiz", "Variables Practical"],
            [assessment.assessment_name for assessment in report.assessments],
        )
        self.assertEqual(2, report.performance_summary.assessment_count)
        self.assertEqual(6, report.performance_summary.expected_result_count)
        self.assertEqual(4, report.performance_summary.recorded_result_count)
        self.assertEqual(3, report.performance_summary.missing_result_count)
        self.assertEqual(1, report.performance_summary.pass_count)
        self.assertEqual(2, report.performance_summary.fail_count)
        self.assertEqual(1, report.performance_summary.unclassified_count)
        self.assertEqual(
            Decimal("37.21"),
            round_percentage_for_display(report.performance_summary.average_percentage),
        )

        sql_report = self.service.get_course_overview("SQL101")
        self.assertEqual(["Select Drill"], [assessment.assessment_name for assessment in sql_report.assessments])
        self.assertEqual(1, sql_report.performance_summary.recorded_result_count)

    def test_course_attendance_report_filters_dates_and_validates_range(self):
        seed_reporting_data(self.database_path)

        full = self.service.get_course_attendance_report("PYF101")
        filtered = self.service.get_course_attendance_report(
            "PYF101",
            date_from="2026-09-03",
            date_to="2026-09-03",
        )

        self.assertEqual(2, len(full.sessions))
        self.assertEqual(2, full.summary.session_count)
        self.assertEqual(["Loops"], [session.topic for session in filtered.sessions])
        self.assertEqual(4, len(filtered.student_summaries))
        filtered_students = {
            row.student.student_number: row
            for row in filtered.student_summaries
        }
        self.assertEqual(0.0, filtered_students["STU-1001"].summary.attendance_percentage)
        self.assertEqual(100.0, filtered_students["STU-1002"].summary.attendance_percentage)
        self.assertIsNone(filtered_students["STU-1003"].summary.attendance_percentage)
        self.assertEqual(4, filtered.summary.record_count)
        self.assertEqual(3, filtered.summary.percentage_denominator)
        self.assertEqual(33.33, filtered.summary.attendance_percentage)
        with self.assertRaisesRegex(ValidationError, "Date from"):
            self.service.get_course_attendance_report(
                "PYF101",
                date_from="2026-09-04",
                date_to="2026-09-03",
            )

    def test_low_attendance_threshold_is_strict_and_keeps_no_denominator_separate(self):
        seed_reporting_data(self.database_path)

        at_equal_threshold = self.service.get_low_attendance_students("PYF101", "50")
        high_threshold = self.service.get_low_attendance_students("PYF101", "100")
        zero_threshold = self.service.get_low_attendance_students("PYF101", "0")

        self.assertEqual((), at_equal_threshold.students_below_threshold)
        self.assertEqual(
            ["STU-1003"],
            [
                row.student.student_number
                for row in at_equal_threshold.students_without_calculable_attendance
            ],
        )
        self.assertEqual(
            ["STU-1002", "STU-1001"],
            [row.student.student_number for row in high_threshold.students_below_threshold],
        )
        self.assertEqual((), zero_threshold.students_below_threshold)
        with self.assertRaisesRegex(ValidationError, "between 0 and 100"):
            self.service.get_low_attendance_students("PYF101", "-1")
        with self.assertRaisesRegex(ValidationError, "between 0 and 100"):
            self.service.get_low_attendance_students("PYF101", "101")
        for threshold in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(threshold=threshold):
                with self.assertRaisesRegex(ValidationError, "finite number"):
                    self.service.get_low_attendance_students("PYF101", threshold)

    def test_assessment_performance_reports_missing_zero_pass_fail_and_history(self):
        fixture = seed_reporting_data(self.database_path)

        report = self.service.get_assessment_performance(
            fixture.assessment_practical.assessment_id
        )

        self.assertEqual("Variables Practical", report.assessment.assessment_name)
        self.assertEqual(4, len(report.students))
        self.assertEqual(3, report.summary.expected_result_count)
        self.assertEqual(3, report.summary.recorded_result_count)
        self.assertEqual(1, report.summary.missing_result_count)
        self.assertEqual(1, report.summary.pass_count)
        self.assertEqual(2, report.summary.fail_count)
        self.assertEqual(0, report.summary.unclassified_count)
        self.assertEqual(Decimal("38.50"), round_percentage_for_display(report.summary.average_percentage))

        rows = {row.student.student_number: row for row in report.students}
        self.assertEqual(Decimal("0"), rows["STU-1001"].mark_obtained)
        self.assertEqual("fail", rows["STU-1001"].result_state)
        self.assertTrue(rows["STU-1003"].is_missing)
        self.assertFalse(rows["STU-1005"].is_currently_eligible)
        self.assertEqual("fail", rows["STU-1005"].result_state)

    def test_assessment_performance_without_pass_mark_is_unclassified(self):
        fixture = seed_reporting_data(self.database_path)

        report = self.service.get_assessment_performance(
            fixture.assessment_quiz.assessment_id
        )

        self.assertEqual(3, report.summary.expected_result_count)
        self.assertEqual(1, report.summary.recorded_result_count)
        self.assertEqual(2, report.summary.missing_result_count)
        self.assertIsNone(report.summary.pass_count)
        self.assertIsNone(report.summary.fail_count)
        self.assertEqual(1, report.summary.unclassified_count)
        self.assertEqual(Decimal("33.33"), round_percentage_for_display(report.summary.average_percentage))

    def test_assessment_performance_handles_not_found_and_no_results(self):
        students = StudentService(self.database_path)
        courses = CourseService(self.database_path)
        enrolments = CourseEnrolmentService(self.database_path)
        assessments = AssessmentService(self.database_path)
        students.register_student("STU-2001", "Faye", "Botha")
        courses.create_course("REP101", "Reporting", fee_amount="0", status="active")
        enrolments.enrol_student("STU-2001", "REP101", "2026-09-01")
        assessment = assessments.create_assessment("REP101", "Empty Test", "test", "10", pass_mark="5")

        report = self.service.get_assessment_performance(assessment.assessment_id)

        self.assertEqual(1, report.summary.expected_result_count)
        self.assertEqual(0, report.summary.recorded_result_count)
        self.assertEqual(1, report.summary.missing_result_count)
        self.assertEqual(0, report.summary.pass_count)
        self.assertEqual(0, report.summary.fail_count)
        self.assertIsNone(report.summary.average_percentage)
        with self.assertRaisesRegex(RecordNotFoundError, "No assessment"):
            self.service.get_assessment_performance(999)

    def test_decimal_percentages_use_exact_decimal_values(self):
        students = StudentService(self.database_path)
        courses = CourseService(self.database_path)
        enrolments = CourseEnrolmentService(self.database_path)
        assessments = AssessmentService(self.database_path)
        students.register_student("STU-3001", "Gita", "Maseko")
        courses.create_course("DEC101", "Decimal Maths", fee_amount="0", status="active")
        enrolments.enrol_student("STU-3001", "DEC101", "2026-09-01")
        repeating = assessments.create_assessment("DEC101", "Repeating", "quiz", "0.3")
        fractional = assessments.create_assessment("DEC101", "Fractional", "quiz", "1.25")
        assessments.record_mark(repeating.assessment_id, "STU-3001", "0.1")
        assessments.record_mark(fractional.assessment_id, "STU-3001", "0.5")

        repeating_report = self.service.get_assessment_performance(repeating.assessment_id)
        fractional_report = self.service.get_assessment_performance(fractional.assessment_id)

        self.assertEqual(
            (Decimal("0.1") / Decimal("0.3")) * Decimal("100"),
            repeating_report.students[0].percentage,
        )
        self.assertEqual(
            Decimal("33.33"),
            round_percentage_for_display(repeating_report.students[0].percentage),
        )
        self.assertEqual(Decimal("40"), fractional_report.students[0].percentage)

    def test_trainer_assignment_report_splits_active_and_historical_course_only(self):
        fixture = seed_reporting_data(self.database_path)
        trainers = TrainerService(self.database_path)
        trainers.register_trainer("TRN-9999", "No", "Assignments")

        report = self.service.get_trainer_assignment_report("TRN-1001")
        empty = self.service.get_trainer_assignment_report("TRN-9999")
        historical = self.service.get_trainer_assignment_report("TRN-1002")

        self.assertEqual(fixture.trainer_thandi.trainer_id, report.trainer.trainer_id)
        self.assertEqual(["PYF101", "SQL101"], [row.course_code for row in report.active_assignments])
        self.assertEqual((), report.ended_assignments)
        self.assertEqual((), empty.active_assignments)
        self.assertEqual((), empty.ended_assignments)
        self.assertEqual(["PYF101"], [row.course_code for row in historical.ended_assignments])
        with self.assertRaisesRegex(RecordNotFoundError, "No trainer"):
            self.service.get_trainer_assignment_report("TRN-404")

    def test_report_generation_is_read_only(self):
        fixture = seed_reporting_data(self.database_path)
        before = operational_table_counts(self.database_path)

        self.service.get_system_overview()
        self.service.get_student_progress("STU-1001")
        self.service.get_course_overview("PYF101")
        self.service.get_course_attendance_report("PYF101")
        self.service.get_low_attendance_students("PYF101", "80")
        self.service.get_assessment_performance(fixture.assessment_practical.assessment_id)
        self.service.get_trainer_assignment_report("TRN-1001")

        self.assertEqual(before, operational_table_counts(self.database_path))


if __name__ == "__main__":
    unittest.main()
