"""Integration tests for assessment service business behavior."""

from decimal import Decimal
import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.assessment import (
    ASSESSMENT_ACTIVE_STATUS,
    ASSESSMENT_ARCHIVED_STATUS,
)
from itca_training_centre.models.course import (
    COURSE_ACTIVE_STATUS,
    COURSE_PLANNED_STATUS,
)
from itca_training_centre.models.mark import (
    RESULT_FAIL_STATE,
    RESULT_PASS_STATE,
    MarkCaptureEntry,
)
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


class AssessmentServiceTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.student_service = StudentService(self.database_path)
        self.course_service = CourseService(self.database_path)
        self.module_service = ModuleService(self.database_path)
        self.enrolment_service = CourseEnrolmentService(self.database_path)
        self.service = AssessmentService(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def _create_student(
        self,
        student_number="STU-1001",
        first_name="Amina",
        last_name="Nkosi",
    ):
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

    def _create_module(self, course_code="PYF101", module_code="MOD-101", sequence=1):
        return self.module_service.create_module(
            course_code,
            module_code,
            f"{module_code} Module",
            sequence,
        )

    def _enrol(self, student_number="STU-1001", course_code="PYF101"):
        return self.enrolment_service.enrol_student(
            student_number,
            course_code,
            "2026-09-01",
        )

    def _create_assessment(
        self,
        course_code="PYF101",
        assessment_name="Final Exam",
        assessment_type="exam",
        max_mark="100",
        module_code=None,
        pass_mark=None,
    ):
        return self.service.create_assessment(
            course_code=course_code,
            module_code=module_code,
            assessment_name=assessment_name,
            assessment_type=assessment_type,
            max_mark=max_mark,
            pass_mark=pass_mark,
        )

    def test_create_assessment_validates_course_and_optional_module_target(self):
        course = self._create_course()
        module = self._create_module()

        course_level = self._create_assessment(assessment_name="Final Exam")
        module_specific = self._create_assessment(
            assessment_name="Variables Practical",
            assessment_type="practical",
            max_mark="75.50",
            module_code=" mod-101 ",
            pass_mark="50",
        )

        self.assertEqual(course.course_id, course_level.course_id)
        self.assertIsNone(course_level.module_id)
        self.assertTrue(course_level.is_course_level)
        self.assertEqual(module.module_id, module_specific.module_id)
        self.assertTrue(module_specific.is_module_specific)
        self.assertEqual(Decimal("75.50"), module_specific.max_mark)

        with self.assertRaisesRegex(RecordNotFoundError, "No course"):
            self._create_assessment(course_code="MISSING")

        self._create_course("PLN101", status=COURSE_PLANNED_STATUS)
        with self.assertRaisesRegex(ValidationError, "Course must be active"):
            self._create_assessment(course_code="PLN101")

        self._create_course("SQL101")
        self._create_module("SQL101", "MOD-201", 1)
        with self.assertRaisesRegex(RecordNotFoundError, "No module"):
            self._create_assessment(module_code="MOD-201")

        self.module_service.deactivate_module("PYF101", "MOD-101")
        with self.assertRaisesRegex(ValidationError, "Module must be active"):
            self._create_assessment(module_code="MOD-101")

    def test_create_assessment_validates_decimal_fields(self):
        self._create_course()

        for max_mark in ["0", "-1", "not-a-number", "NaN", "Infinity"]:
            with self.subTest(max_mark=max_mark):
                with self.assertRaises(ValidationError):
                    self._create_assessment(max_mark=max_mark)

        with self.assertRaisesRegex(ValidationError, "weight"):
            self.service.create_assessment(
                "PYF101",
                "Weighted Quiz",
                "quiz",
                "20",
                weight="-0.1",
            )
        with self.assertRaisesRegex(ValidationError, "Pass mark"):
            self.service.create_assessment(
                "PYF101",
                "Impossible Quiz",
                "quiz",
                "20",
                pass_mark="21",
            )
        with self.assertRaisesRegex(ValidationError, "Pass mark"):
            self.service.create_assessment(
                "PYF101",
                "Negative Pass",
                "quiz",
                "20",
                pass_mark="-1",
            )

        fractional = self.service.create_assessment(
            "PYF101",
            "Fractional Practical",
            "practical",
            "1.25",
            pass_mark="0.75",
        )
        self.assertEqual(Decimal("1.25"), fractional.max_mark)
        self.assertEqual(Decimal("0.75"), fractional.pass_mark)

    def test_mark_capture_requires_eligibility_active_assessment_and_valid_range(self):
        self._create_course()
        self._create_student("STU-1001", "Amina", "Nkosi")
        self._create_student("STU-1002", "Bongi", "Mokoena")
        self._enrol("STU-1001")
        assessment = self._create_assessment(max_mark="10")

        zero_mark = self.service.record_mark(
            assessment.assessment_id,
            " stu-1001 ",
            "0",
            "Submitted blank file",
        )

        self.assertEqual(Decimal("0"), zero_mark.mark_obtained)
        self.assertEqual("Submitted blank file", zero_mark.notes)
        with self.assertRaisesRegex(DuplicateRecordError, "already recorded"):
            self.service.record_mark(assessment.assessment_id, "STU-1001", "5")
        with self.assertRaisesRegex(ValidationError, "not eligible"):
            self.service.record_mark(assessment.assessment_id, "STU-1002", "5")
        with self.assertRaisesRegex(RecordNotFoundError, "No student"):
            self.service.record_mark(assessment.assessment_id, "STU-9999", "5")
        with self.assertRaisesRegex(RecordNotFoundError, "No assessment"):
            self.service.record_mark(999, "STU-1001", "5")

        range_assessment = self._create_assessment(
            assessment_name="Range Test",
            assessment_type="test",
            max_mark="10",
        )
        for mark in ["-0.1", "10.01", "not-a-number", "NaN", "Infinity"]:
            with self.subTest(mark=mark):
                with self.assertRaises(ValidationError):
                    self.service.record_mark(
                        range_assessment.assessment_id,
                        "STU-1001",
                        mark,
                    )
        self.assertEqual(
            [],
            self.service.list_assessment_results(range_assessment.assessment_id),
        )

        max_mark = self.service.record_mark(
            range_assessment.assessment_id,
            "STU-1001",
            "10",
        )
        self.assertEqual(Decimal("10"), max_mark.mark_obtained)

        archived_assessment = self._create_assessment(
            assessment_name="Archived Assessment",
            assessment_type="quiz",
            max_mark="5",
        )
        self.service.deactivate_assessment(archived_assessment.assessment_id)
        with self.assertRaisesRegex(ValidationError, "Assessment must be active"):
            self.service.record_mark(
                archived_assessment.assessment_id,
                "STU-1001",
                "5",
            )

    def test_mark_correction_preserves_id_and_allows_zero_and_maximum(self):
        self._create_course()
        self._create_student()
        self._create_student("STU-1002", "Bongi", "Mokoena")
        self._enrol()
        assessment = self._create_assessment(max_mark="10")
        created = self.service.record_mark(assessment.assessment_id, "STU-1001", "4")

        corrected_zero = self.service.correct_mark(
            assessment.assessment_id,
            "STU-1001",
            "0",
            "Correction to zero",
        )
        corrected_max = self.service.correct_mark(
            assessment.assessment_id,
            "STU-1001",
            "10",
            None,
        )

        self.assertEqual(created.mark_id, corrected_zero.mark_id)
        self.assertEqual(created.mark_id, corrected_max.mark_id)
        self.assertEqual(Decimal("0"), corrected_zero.mark_obtained)
        self.assertEqual(Decimal("10"), corrected_max.mark_obtained)
        self.assertIsNone(corrected_max.notes)
        with self.assertRaisesRegex(ValidationError, "between 0 and 10"):
            self.service.correct_mark(assessment.assessment_id, "STU-1001", "10.5")
        with self.assertRaisesRegex(RecordNotFoundError, "No result"):
            self.service.correct_mark(assessment.assessment_id, "STU-1002", "5")

        current = self.service.get_mark(assessment.assessment_id, "STU-1001")
        self.assertEqual(created.mark_id, current.mark_id)
        self.assertEqual(Decimal("10"), current.mark_obtained)

    def test_percentage_pass_fail_and_summary_calculations_use_decimal(self):
        self._create_course()
        self._create_student("STU-1001", "Amina", "Nkosi")
        self._create_student("STU-1002", "Bongi", "Mokoena")
        self._enrol("STU-1001")
        self._enrol("STU-1002")
        assessment = self._create_assessment(max_mark="3", pass_mark="2")
        self.service.record_mark(assessment.assessment_id, "STU-1001", "1")
        self.service.record_mark(assessment.assessment_id, "STU-1002", "3")

        results = self.service.list_assessment_results(assessment.assessment_id)
        percentages = {
            result.mark.mark_obtained: result.percentage
            for result in results
        }
        states = {
            result.mark.mark_obtained: result.result_state
            for result in results
        }
        summary = self.service.calculate_assessment_summary(assessment.assessment_id)

        self.assertEqual((Decimal("1") / Decimal("3")) * Decimal("100"), percentages[Decimal("1")])
        self.assertEqual(Decimal("33.33"), round_percentage_for_display(percentages[Decimal("1")]))
        self.assertEqual(Decimal("100"), percentages[Decimal("3")])
        self.assertEqual(RESULT_FAIL_STATE, states[Decimal("1")])
        self.assertEqual(RESULT_PASS_STATE, states[Decimal("3")])
        self.assertEqual(2, summary.recorded_count)
        self.assertEqual(Decimal("2"), summary.average_mark)
        self.assertEqual(Decimal("66.67"), round_percentage_for_display(summary.average_percentage))
        self.assertEqual(Decimal("3"), summary.highest_mark)
        self.assertEqual(Decimal("1"), summary.lowest_mark)
        self.assertEqual(1, summary.pass_count)
        self.assertEqual(1, summary.fail_count)
        self.assertEqual(Decimal("50"), summary.pass_rate)

    def test_missing_pass_rule_keeps_result_state_undefined(self):
        self._create_course()
        self._create_student()
        self._enrol()
        assessment = self.service.create_assessment(
            "PYF101",
            "Practice Drill",
            "practical",
            "10",
            pass_mark=None,
        )

        empty_summary = self.service.calculate_assessment_summary(
            assessment.assessment_id
        )
        mark = self.service.record_mark(assessment.assessment_id, "STU-1001", "7")
        result = self.service.list_assessment_results(assessment.assessment_id)[0]
        summary = self.service.calculate_assessment_summary(assessment.assessment_id)

        self.assertEqual(0, empty_summary.recorded_count)
        self.assertIsNone(empty_summary.average_mark)
        self.assertIsNone(empty_summary.pass_count)
        self.assertEqual(mark.mark_id, result.mark.mark_id)
        self.assertIsNone(result.result_state)
        self.assertIsNone(summary.pass_count)
        self.assertIsNone(summary.fail_count)
        self.assertIsNone(summary.pass_rate)

    def test_class_capture_preserves_zero_missing_mark_and_atomic_failure(self):
        self._create_course()
        self._create_student("STU-1001", "Amina", "Nkosi")
        self._create_student("STU-1002", "Bongi", "Mokoena")
        self._create_student("STU-1003", "Celia", "Zulu")
        for student_number in ["STU-1001", "STU-1002", "STU-1003"]:
            self._enrol(student_number)
        assessment = self._create_assessment(max_mark="10")

        eligible = self.service.list_eligible_students(assessment.assessment_id)
        self.assertEqual(
            ["STU-1002", "STU-1001", "STU-1003"],
            [student.student_number for student in eligible],
        )

        with self.assertRaisesRegex(ValidationError, "between 0 and 10"):
            self.service.record_class_marks(
                assessment.assessment_id,
                [
                    MarkCaptureEntry("STU-1001", "5"),
                    MarkCaptureEntry("STU-1002", "10.01"),
                ],
            )
        self.assertEqual([], self.service.list_assessment_results(assessment.assessment_id))

        marks = self.service.record_class_marks(
            assessment.assessment_id,
            [
                MarkCaptureEntry("STU-1002", "0", "Explicit zero"),
                MarkCaptureEntry("STU-1001", "7.5"),
            ],
        )
        self.assertEqual(2, len(marks))
        self.assertEqual(
            [Decimal("0"), Decimal("7.5")],
            [mark.mark_obtained for mark in marks],
        )
        with self.assertRaisesRegex(RecordNotFoundError, "No result"):
            self.service.get_mark(assessment.assessment_id, "STU-1003")

        duplicate_assessment = self._create_assessment(
            assessment_name="Duplicate Guard",
            assessment_type="quiz",
            max_mark="10",
        )
        self.service.record_mark(duplicate_assessment.assessment_id, "STU-1001", "8")
        with self.assertRaisesRegex(DuplicateRecordError, "already recorded"):
            self.service.record_class_marks(
                duplicate_assessment.assessment_id,
                [
                    MarkCaptureEntry("STU-1003", "6"),
                    MarkCaptureEntry("STU-1001", "9"),
                ],
            )
        with self.assertRaisesRegex(DuplicateRecordError, "more than once"):
            self.service.record_class_marks(
                duplicate_assessment.assessment_id,
                [
                    MarkCaptureEntry("STU-1002", "5"),
                    MarkCaptureEntry("stu-1002", "6"),
                ],
            )
        with self.assertRaisesRegex(RecordNotFoundError, "No result"):
            self.service.get_mark(duplicate_assessment.assessment_id, "STU-1003")

    def test_update_assessment_clears_optional_fields_and_protects_existing_marks(self):
        self._create_course()
        self._create_student()
        self._enrol()
        assessment = self.service.create_assessment(
            "PYF101",
            "Original Quiz",
            "quiz",
            "100",
            weight="25",
            pass_mark="50",
        )
        self.service.record_mark(assessment.assessment_id, "STU-1001", "75")

        with self.assertRaisesRegex(ValidationError, "below existing"):
            self.service.update_assessment(assessment.assessment_id, max_mark="70")

        updated = self.service.update_assessment(
            assessment.assessment_id,
            assessment_name="Updated Project",
            assessment_type="project",
            max_mark="120",
            weight=None,
            pass_mark=None,
            status=ASSESSMENT_ARCHIVED_STATUS,
        )

        self.assertEqual(assessment.assessment_id, updated.assessment_id)
        self.assertEqual("Updated Project", updated.assessment_name)
        self.assertEqual("project", updated.assessment_type)
        self.assertEqual(Decimal("120"), updated.max_mark)
        self.assertIsNone(updated.weight)
        self.assertIsNone(updated.pass_mark)
        self.assertEqual(ASSESSMENT_ARCHIVED_STATUS, updated.status)

    def test_historical_results_survive_later_status_changes(self):
        student = self._create_student()
        course = self._create_course()
        module = self._create_module()
        self._enrol()
        assessment = self._create_assessment(
            assessment_name="Variables Practical",
            assessment_type="practical",
            max_mark="100",
            module_code="MOD-101",
        )
        mark = self.service.record_mark(assessment.assessment_id, "STU-1001", "70")

        self.enrolment_service.cancel_enrolment(
            "STU-1001",
            "PYF101",
            "2026-09-05",
            "Student withdrew",
        )
        self.student_service.deactivate_student("STU-1001")
        self.module_service.deactivate_module("PYF101", "MOD-101")
        self.course_service.deactivate_course("PYF101")
        self.service.deactivate_assessment(assessment.assessment_id)
        corrected = self.service.correct_mark(
            assessment.assessment_id,
            "STU-1001",
            "80",
        )

        history = self.service.list_student_result_history("STU-1001", "PYF101")
        results = self.service.list_assessment_results(assessment.assessment_id)
        with open_database(self.database_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM marks").fetchone()[0]

        self.assertEqual(student.student_id, mark.student_id)
        self.assertEqual(course.course_id, assessment.course_id)
        self.assertEqual(module.module_id, assessment.module_id)
        self.assertEqual(mark.mark_id, corrected.mark_id)
        self.assertEqual([mark.mark_id], [result.mark.mark_id for result in history])
        self.assertEqual([mark.mark_id], [result.mark.mark_id for result in results])
        self.assertEqual(1, count)
        self.assertEqual(ASSESSMENT_ARCHIVED_STATUS, self.service.get_assessment(assessment.assessment_id).status)


if __name__ == "__main__":
    unittest.main()
