"""Integration tests for assessment mark persistence."""

from decimal import Decimal
import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.course import COURSE_ACTIVE_STATUS
from itca_training_centre.repositories.assessment_repository import (
    AssessmentRepository,
)
from itca_training_centre.repositories.course_repository import CourseRepository
from itca_training_centre.repositories.mark_repository import MarkRepository
from itca_training_centre.repositories.module_repository import ModuleRepository
from itca_training_centre.repositories.student_repository import StudentRepository
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
)
from tests.helpers import temporary_database_path


class MarkRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.student_repository = StudentRepository(self.database_path)
        self.course_repository = CourseRepository(self.database_path)
        self.module_repository = ModuleRepository(self.database_path)
        self.assessment_repository = AssessmentRepository(self.database_path)
        self.repository = MarkRepository(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def _create_student(self, student_number="STU-1001", first_name="Amina", last_name="Nkosi"):
        return self.student_repository.create(
            student_number,
            first_name,
            last_name,
            None,
            None,
        )

    def _create_course(self, course_code="PYF101"):
        return self.course_repository.create(
            course_code,
            f"{course_code} Course",
            None,
            Decimal("0"),
            COURSE_ACTIVE_STATUS,
        )

    def _create_assessment(self, course=None, name="Final Exam", max_mark=Decimal("100")):
        course = course or self._create_course()
        return self.assessment_repository.create(
            course.course_id,
            None,
            name,
            "exam",
            max_mark,
        )

    def test_create_mark_round_trips_decimal_text_and_lookup_methods(self):
        student = self._create_student()
        assessment = self._create_assessment(max_mark=Decimal("75.50"))

        mark = self.repository.create(
            assessment.assessment_id,
            student.student_id,
            Decimal("75.50"),
            "Excellent",
        )

        by_id = self.repository.get_by_id(mark.mark_id)
        by_relationship = self.repository.get_for_student_assessment(
            assessment.assessment_id,
            student.student_id,
        )
        with open_database(self.database_path) as connection:
            stored = connection.execute(
                "SELECT mark_obtained FROM marks WHERE mark_id = ?",
                (mark.mark_id,),
            ).fetchone()["mark_obtained"]

        self.assertEqual(mark, by_id)
        self.assertEqual(mark, by_relationship)
        self.assertEqual(Decimal("75.50"), mark.mark_obtained)
        self.assertEqual("75.5", stored)
        self.assertTrue(mark.captured_at.endswith("Z"))

    def test_missing_mark_returns_none(self):
        self.assertIsNone(self.repository.get_by_id(999))
        self.assertIsNone(self.repository.get_for_student_assessment(1, 1))

    def test_list_for_assessment_orders_by_student_name(self):
        course = self._create_course()
        assessment = self._create_assessment(course)
        zulu = self._create_student("STU-1003", "Celia", "Zulu")
        nkosi = self._create_student("STU-1001", "Amina", "Nkosi")
        mokoena = self._create_student("STU-1002", "Bongi", "Mokoena")
        self.repository.create(assessment.assessment_id, zulu.student_id, Decimal("60"))
        self.repository.create(assessment.assessment_id, nkosi.student_id, Decimal("70"))
        self.repository.create(assessment.assessment_id, mokoena.student_id, Decimal("80"))

        marks = self.repository.list_for_assessment(assessment.assessment_id)

        self.assertEqual(
            [mokoena.student_id, nkosi.student_id, zulu.student_id],
            [mark.student_id for mark in marks],
        )

    def test_list_for_student_orders_by_course_module_and_assessment(self):
        student = self._create_student()
        python_course = self._create_course("PYF101")
        sql_course = self._create_course("SQL101")
        python_module = self.module_repository.create(
            python_course.course_id,
            "MOD-101",
            "Variables",
            1,
        )
        sql_exam = self._create_assessment(sql_course, "SQL Exam")
        python_exam = self._create_assessment(python_course, "Python Exam")
        python_quiz = self.assessment_repository.create(
            python_course.course_id,
            python_module.module_id,
            "Variables Quiz",
            "quiz",
            Decimal("20"),
        )
        for assessment in (sql_exam, python_quiz, python_exam):
            self.repository.create(
                assessment.assessment_id,
                student.student_id,
                Decimal("10"),
            )

        all_marks = self.repository.list_for_student(student.student_id)
        python_marks = self.repository.list_for_student(
            student.student_id,
            course_id=python_course.course_id,
        )

        self.assertEqual(
            [
                python_exam.assessment_id,
                python_quiz.assessment_id,
                sql_exam.assessment_id,
            ],
            [mark.assessment_id for mark in all_marks],
        )
        self.assertEqual(
            [python_exam.assessment_id, python_quiz.assessment_id],
            [mark.assessment_id for mark in python_marks],
        )

    def test_duplicate_student_assessment_mark_is_rejected(self):
        student = self._create_student()
        assessment = self._create_assessment()
        self.repository.create(assessment.assessment_id, student.student_id, Decimal("80"))

        with self.assertRaisesRegex(DuplicateRecordError, "already recorded"):
            self.repository.create(
                assessment.assessment_id,
                student.student_id,
                Decimal("85"),
            )

    def test_update_preserves_mark_id_and_exact_decimal_value(self):
        student = self._create_student()
        assessment = self._create_assessment(max_mark=Decimal("1.25"))
        mark = self.repository.create(
            assessment.assessment_id,
            student.student_id,
            Decimal("0.1"),
        )

        updated = self.repository.update(mark.mark_id, Decimal("1.25"), "Corrected")

        self.assertEqual(mark.mark_id, updated.mark_id)
        self.assertEqual(Decimal("1.25"), updated.mark_obtained)
        self.assertEqual("Corrected", updated.notes)

    def test_foreign_key_constraints_are_friendly_errors(self):
        student = self._create_student()
        assessment = self._create_assessment()

        with self.assertRaisesRegex(RecordNotFoundError, "Assessment or student"):
            self.repository.create(999, student.student_id, Decimal("50"))

        with self.assertRaisesRegex(RecordNotFoundError, "Assessment or student"):
            self.repository.create(assessment.assessment_id, 999, Decimal("50"))

    def test_create_many_rolls_back_when_one_row_violates_uniqueness(self):
        student = self._create_student()
        assessment = self._create_assessment()

        with self.assertRaisesRegex(DuplicateRecordError, "already recorded"):
            self.repository.create_many(
                [
                    (assessment.assessment_id, student.student_id, Decimal("50"), None),
                    (assessment.assessment_id, student.student_id, Decimal("60"), None),
                ]
            )

        self.assertEqual([], self.repository.list_for_assessment(assessment.assessment_id))


if __name__ == "__main__":
    unittest.main()
