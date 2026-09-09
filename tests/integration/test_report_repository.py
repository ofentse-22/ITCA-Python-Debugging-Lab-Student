"""Integration tests for report repository read queries."""

from decimal import Decimal
import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.repositories.report_repository import ReportRepository
from tests.helpers import temporary_database_path
from tests.reporting_helpers import operational_table_counts, seed_reporting_data


class ReportRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.repository = ReportRepository(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_system_overview_returns_zero_counts_for_empty_database(self):
        overview = self.repository.get_system_overview()

        self.assertEqual(0, overview.student_count)
        self.assertEqual(0, overview.course_count)
        self.assertEqual(0, overview.enrolment_count)
        self.assertEqual(0, overview.attendance_record_count)
        self.assertEqual(0, overview.assessment_count)
        self.assertEqual(0, overview.mark_count)

    def test_system_overview_counts_populated_active_and_historical_rows(self):
        seed_reporting_data(self.database_path)

        overview = self.repository.get_system_overview()

        self.assertEqual(6, overview.student_count)
        self.assertEqual(5, overview.active_student_count)
        self.assertEqual(1, overview.inactive_student_count)
        self.assertEqual(2, overview.course_count)
        self.assertEqual(2, overview.active_course_count)
        self.assertEqual(2, overview.trainer_count)
        self.assertEqual(5, overview.enrolment_count)
        self.assertEqual(4, overview.active_enrolment_count)
        self.assertEqual(1, overview.cancelled_enrolment_count)
        self.assertEqual(3, overview.trainer_assignment_count)
        self.assertEqual(2, overview.active_trainer_assignment_count)
        self.assertEqual(1, overview.ended_trainer_assignment_count)
        self.assertEqual(2, overview.attendance_session_count)
        self.assertEqual(8, overview.attendance_record_count)
        self.assertEqual(3, overview.assessment_count)
        self.assertEqual(2, overview.active_assessment_count)
        self.assertEqual(1, overview.archived_assessment_count)
        self.assertEqual(5, overview.mark_count)

    def test_student_course_and_trainer_lookups_normalized_by_service_inputs(self):
        fixture = seed_reporting_data(self.database_path)

        student = self.repository.get_student_by_number("STU-1001")
        course = self.repository.get_course_by_code("PYF101")
        trainer = self.repository.get_trainer_by_number("TRN-1001")
        assessment = self.repository.get_assessment_by_id(
            fixture.assessment_practical.assessment_id
        )

        self.assertEqual("Amina Nkosi", student.full_name)
        self.assertEqual("Python Fundamentals", course.course_name)
        self.assertEqual("Thandi Dlamini", trainer.full_name)
        self.assertEqual("PYF101", assessment.course_code)
        self.assertEqual("MOD-101 - Variables", assessment.module_label)
        self.assertEqual(Decimal("100"), assessment.max_mark)

    def test_enrolment_filters_include_history_and_deterministic_order(self):
        fixture = seed_reporting_data(self.database_path)

        student_enrolments = self.repository.list_student_enrolments(
            fixture.student_esi.student_id
        )
        course_enrolments = self.repository.list_course_enrolments(
            fixture.course_python.course_id
        )
        active_students = self.repository.list_active_students_for_course(
            fixture.course_python.course_id
        )

        self.assertEqual(["cancelled"], [row.status for row in student_enrolments])
        self.assertEqual(
            ["STU-1005", "STU-1002", "STU-1001", "STU-1003"],
            [row.student_number for row in course_enrolments],
        )
        self.assertEqual(
            ["STU-1002", "STU-1001", "STU-1003"],
            [student.student_number for student in active_students],
        )

    def test_attendance_queries_return_actual_status_counts(self):
        fixture = seed_reporting_data(self.database_path)

        records = self.repository.list_attendance_records_for_course(
            fixture.course_python.course_id
        )
        sessions = self.repository.list_attendance_sessions_for_course(
            fixture.course_python.course_id
        )

        self.assertEqual(8, len(records))
        self.assertEqual(
            ["Control Flow", "Loops"],
            [session.topic for session in sessions],
        )
        self.assertEqual(4, sessions[0].record_count)
        self.assertEqual(2, sessions[0].present_count)
        self.assertEqual(1, sessions[0].absent_count)
        self.assertEqual(1, sessions[0].unknown_count)
        self.assertEqual(1, sessions[1].late_count)
        self.assertEqual(2, sessions[1].absent_count)
        self.assertEqual(1, sessions[1].excused_count)

    def test_assessment_queries_preserve_zero_missing_and_no_cross_course_leakage(self):
        fixture = seed_reporting_data(self.database_path)

        amina_sources = self.repository.list_student_assessment_sources(
            fixture.student_amina.student_id
        )
        celia_sources = self.repository.list_student_assessment_sources(
            fixture.student_celia.student_id
        )
        marks = self.repository.list_marks_for_assessment(
            fixture.assessment_practical.assessment_id
        )

        self.assertEqual(
            ["Course Quiz", "Variables Practical"],
            [source.assessment.assessment_name for source in amina_sources],
        )
        self.assertEqual(Decimal("1"), amina_sources[0].mark_obtained)
        self.assertEqual(Decimal("0"), amina_sources[1].mark_obtained)
        self.assertEqual(
            [None, None],
            [source.mark_obtained for source in celia_sources],
        )
        self.assertEqual(
            ["STU-1005", "STU-1002", "STU-1001"],
            [source.student.student_number for source in marks],
        )

    def test_trainer_assignment_queries_split_active_and_historical_context(self):
        fixture = seed_reporting_data(self.database_path)

        course_assignments = self.repository.list_trainer_assignments_for_course(
            fixture.course_python.course_id
        )
        trainer_assignments = self.repository.list_trainer_assignments_for_trainer(
            fixture.trainer_thandi.trainer_id
        )

        self.assertEqual(
            ["TRN-1001", "TRN-1002"],
            [assignment.trainer_number for assignment in course_assignments],
        )
        self.assertEqual(
            ["active", "ended"],
            [assignment.status for assignment in course_assignments],
        )
        self.assertEqual(
            ["PYF101", "SQL101"],
            [assignment.course_code for assignment in trainer_assignments],
        )

    def test_repository_report_reads_do_not_mutate_operational_tables(self):
        fixture = seed_reporting_data(self.database_path)
        before = operational_table_counts(self.database_path)

        self.repository.get_system_overview()
        self.repository.get_student_by_number("STU-1001")
        self.repository.get_course_by_code("PYF101")
        self.repository.get_trainer_by_number("TRN-1001")
        self.repository.get_assessment_by_id(fixture.assessment_practical.assessment_id)
        self.repository.list_student_enrolments(fixture.student_amina.student_id)
        self.repository.list_course_enrolments(fixture.course_python.course_id)
        self.repository.list_attendance_records_for_course(fixture.course_python.course_id)
        self.repository.list_attendance_sessions_for_course(fixture.course_python.course_id)
        self.repository.list_student_assessment_sources(fixture.student_amina.student_id)
        self.repository.list_marks_for_assessment(fixture.assessment_practical.assessment_id)
        self.repository.list_trainer_assignments_for_trainer(fixture.trainer_thandi.trainer_id)

        self.assertEqual(before, operational_table_counts(self.database_path))


if __name__ == "__main__":
    unittest.main()
