"""End-to-end Phase 7 assessment and marks workflow tests."""

from decimal import Decimal
import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.mark import MarkCaptureEntry
from itca_training_centre.services.assessment_service import (
    AssessmentService,
    round_percentage_for_display,
)
from itca_training_centre.services.course_enrolment_service import (
    CourseEnrolmentService,
)
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.module_service import ModuleService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from tests.helpers import temporary_database_path


class PhaseSevenAssessmentWorkflowTests(unittest.TestCase):
    def test_complete_assessment_marks_and_history_workflow(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)
            students = StudentService(database_path)
            courses = CourseService(database_path)
            modules = ModuleService(database_path)
            enrolments = CourseEnrolmentService(database_path)
            assessments = AssessmentService(database_path)

            student_a = students.register_student("STU-1001", "Amina", "Nkosi")
            student_b = students.register_student("STU-1002", "Bongi", "Mokoena")
            students.register_student("STU-1003", "Celia", "Zulu")
            course = courses.create_course(
                "PYF101",
                "Python Fundamentals",
                fee_amount="0",
                status="active",
            )
            module = modules.create_module("PYF101", "MOD-101", "Variables", 1)
            enrolments.enrol_student("STU-1001", "PYF101", "2026-09-01")
            enrolments.enrol_student("STU-1002", "PYF101", "2026-09-01")

            assessment_one = assessments.create_assessment(
                "PYF101",
                "Variables Practical",
                "practical",
                "100",
                module_code="MOD-101",
                weight="0.1",
                pass_mark="50",
            )
            mark_a = assessments.record_mark(
                assessment_one.assessment_id,
                "STU-1001",
                Decimal("0"),
            )
            mark_b = assessments.record_mark(
                assessment_one.assessment_id,
                "STU-1002",
                Decimal("75.50"),
            )

            with self.assertRaisesRegex(ValidationError, "not eligible"):
                assessments.record_mark(
                    assessment_one.assessment_id,
                    "STU-1003",
                    "60",
                )
            with self.assertRaisesRegex(DuplicateRecordError, "already recorded"):
                assessments.record_mark(
                    assessment_one.assessment_id,
                    "STU-1001",
                    "80",
                )

            with open_database(database_path) as connection:
                stored_values = [
                    row["mark_obtained"]
                    for row in connection.execute(
                        "SELECT mark_obtained FROM marks ORDER BY mark_id"
                    ).fetchall()
                ]

            self.assertEqual(["0", "75.5"], stored_values)

            results_one = assessments.list_assessment_results(
                assessment_one.assessment_id
            )
            percentages = {
                result.mark.student_id: result.percentage
                for result in results_one
            }
            self.assertEqual(Decimal("0"), percentages[student_a.student_id])
            self.assertEqual(Decimal("75.5"), percentages[student_b.student_id])

            corrected_b = assessments.correct_mark(
                assessment_one.assessment_id,
                "STU-1002",
                "80",
            )
            self.assertEqual(mark_b.mark_id, corrected_b.mark_id)

            assessment_two = assessments.create_assessment(
                "PYF101",
                "Course Quiz",
                "quiz",
                "3",
                pass_mark=None,
            )
            assessments.record_class_marks(
                assessment_two.assessment_id,
                [MarkCaptureEntry("STU-1001", "1")],
            )

            student_a_history = assessments.list_student_result_history("STU-1001")
            assessment_one_results = assessments.list_assessment_results(
                assessment_one.assessment_id
            )
            summary = assessments.calculate_assessment_summary(
                assessment_one.assessment_id
            )

            self.assertEqual(
                [assessment_two.assessment_id, assessment_one.assessment_id],
                [result.assessment.assessment_id for result in student_a_history],
            )
            self.assertEqual(
                [mark_b.mark_id, mark_a.mark_id],
                [result.mark.mark_id for result in assessment_one_results],
            )
            self.assertEqual(2, summary.recorded_count)
            self.assertEqual(Decimal("40"), summary.average_mark)
            self.assertEqual(Decimal("40.00"), round_percentage_for_display(summary.average_percentage))
            self.assertEqual(1, summary.pass_count)
            self.assertEqual(1, summary.fail_count)

            enrolments.cancel_enrolment(
                "STU-1001",
                "PYF101",
                "2026-09-05",
                "Student withdrew",
            )
            students.deactivate_student("STU-1001")
            modules.deactivate_module("PYF101", "MOD-101")
            courses.deactivate_course("PYF101")
            assessments.deactivate_assessment(assessment_one.assessment_id)

            historical_history = assessments.list_student_result_history(
                "STU-1001",
                "PYF101",
            )
            historical_results = assessments.list_assessment_results(
                assessment_one.assessment_id
            )
            with self.assertRaisesRegex(RecordNotFoundError, "No result"):
                assessments.get_mark(assessment_two.assessment_id, "STU-1002")
            with open_database(database_path) as connection:
                mark_count = connection.execute(
                    "SELECT COUNT(*) FROM marks"
                ).fetchone()[0]

            self.assertEqual(
                [3, mark_a.mark_id],
                [result.mark.mark_id for result in historical_history],
            )
            self.assertEqual(
                [mark_b.mark_id, mark_a.mark_id],
                [result.mark.mark_id for result in historical_results],
            )
            self.assertEqual(3, mark_count)
            self.assertEqual(course.course_id, assessment_one.course_id)
            self.assertEqual(module.module_id, assessment_one.module_id)


if __name__ == "__main__":
    unittest.main()
