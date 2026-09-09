"""Integration tests for assessment persistence."""

from decimal import Decimal
import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.assessment import (
    ASSESSMENT_ACTIVE_STATUS,
    ASSESSMENT_ARCHIVED_STATUS,
)
from itca_training_centre.models.course import COURSE_ACTIVE_STATUS
from itca_training_centre.repositories.assessment_repository import (
    AssessmentRepository,
)
from itca_training_centre.repositories.course_repository import CourseRepository
from itca_training_centre.repositories.module_repository import ModuleRepository
from itca_training_centre.utils.exceptions import RecordNotFoundError
from tests.helpers import temporary_database_path


class AssessmentRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.course_repository = CourseRepository(self.database_path)
        self.module_repository = ModuleRepository(self.database_path)
        self.repository = AssessmentRepository(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def _create_course(self, course_code="PYF101"):
        return self.course_repository.create(
            course_code,
            f"{course_code} Course",
            None,
            Decimal("0"),
            COURSE_ACTIVE_STATUS,
        )

    def _create_module(self, course, module_code="MOD-101", sequence_number=1):
        return self.module_repository.create(
            course.course_id,
            module_code,
            f"{module_code} Module",
            sequence_number,
        )

    def test_create_assessment_round_trips_decimal_fields_and_relationships(self):
        course = self._create_course()
        module = self._create_module(course)

        assessment = self.repository.create(
            course_id=course.course_id,
            module_id=module.module_id,
            assessment_name="Variables Practical",
            assessment_type="practical",
            max_mark=Decimal("75.50"),
            weight=Decimal("0.1"),
            pass_mark=Decimal("50.00"),
        )

        self.assertIsInstance(assessment.assessment_id, int)
        self.assertEqual(course.course_id, assessment.course_id)
        self.assertEqual(module.module_id, assessment.module_id)
        self.assertEqual(Decimal("75.50"), assessment.max_mark)
        self.assertEqual(Decimal("0.1"), assessment.weight)
        self.assertEqual(Decimal("50"), assessment.pass_mark)
        self.assertTrue(assessment.created_at.endswith("Z"))
        self.assertTrue(assessment.updated_at.endswith("Z"))

        with open_database(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT max_mark, weight, pass_mark
                FROM assessments
                WHERE assessment_id = ?
                """,
                (assessment.assessment_id,),
            ).fetchone()

        self.assertEqual("75.5", row["max_mark"])
        self.assertEqual("0.1", row["weight"])
        self.assertEqual("50", row["pass_mark"])

    def test_get_missing_assessment_returns_none(self):
        self.assertIsNone(self.repository.get_by_id(999))

    def test_list_filters_by_course_module_status_and_uses_stable_order(self):
        course = self._create_course()
        module_one = self._create_module(course, "MOD-101", 1)
        module_two = self._create_module(course, "MOD-201", 2)
        other_course = self._create_course("SQL101")
        course_level = self.repository.create(
            course.course_id,
            None,
            "Final Exam",
            "exam",
            Decimal("100"),
        )
        first_module = self.repository.create(
            course.course_id,
            module_one.module_id,
            "Variables Quiz",
            "quiz",
            Decimal("20"),
        )
        second_module = self.repository.create(
            course.course_id,
            module_two.module_id,
            "Loops Project",
            "project",
            Decimal("80"),
        )
        archived = self.repository.create(
            course.course_id,
            module_one.module_id,
            "Archived Test",
            "test",
            Decimal("50"),
            status=ASSESSMENT_ARCHIVED_STATUS,
        )
        self.repository.create(
            other_course.course_id,
            None,
            "SQL Exam",
            "exam",
            Decimal("100"),
        )

        course_assessments = self.repository.list_for_course(course.course_id)
        module_assessments = self.repository.list_for_module(module_one.module_id)
        archived_assessments = self.repository.list_for_course(
            course.course_id,
            status=ASSESSMENT_ARCHIVED_STATUS,
        )

        self.assertEqual(
            [
                course_level.assessment_id,
                first_module.assessment_id,
                second_module.assessment_id,
            ],
            [assessment.assessment_id for assessment in course_assessments],
        )
        self.assertEqual(
            [first_module.assessment_id],
            [assessment.assessment_id for assessment in module_assessments],
        )
        self.assertEqual([archived.assessment_id], [item.assessment_id for item in archived_assessments])

    def test_search_uses_supported_assessment_and_parent_fields(self):
        course = self._create_course()
        module = self._create_module(course)
        assessment = self.repository.create(
            course.course_id,
            module.module_id,
            "Variables Practical",
            "practical",
            Decimal("75.50"),
        )
        archived = self.repository.create(
            course.course_id,
            None,
            "Archived Exam",
            "exam",
            Decimal("100"),
            status=ASSESSMENT_ARCHIVED_STATUS,
        )

        for term in ["Variables", "practical", "PYF101", "MOD-101"]:
            with self.subTest(term=term):
                results = self.repository.search(term)
                self.assertEqual([assessment.assessment_id], [item.assessment_id for item in results])

        self.assertEqual([], self.repository.search("Archived"))
        self.assertEqual(
            [archived.assessment_id],
            [
                item.assessment_id
                for item in self.repository.search("Archived", include_archived=True)
            ],
        )

    def test_update_mutable_fields_preserves_course_and_module_targets(self):
        course = self._create_course()
        module = self._create_module(course)
        assessment = self.repository.create(
            course.course_id,
            module.module_id,
            "Variables Quiz",
            "quiz",
            Decimal("20"),
        )

        updated = self.repository.update(
            assessment_id=assessment.assessment_id,
            assessment_name="Variables Practical",
            assessment_type="practical",
            max_mark=Decimal("75.50"),
            weight=Decimal("25.00"),
            pass_mark=Decimal("50.00"),
            status=ASSESSMENT_ACTIVE_STATUS,
        )

        self.assertEqual(assessment.assessment_id, updated.assessment_id)
        self.assertEqual(course.course_id, updated.course_id)
        self.assertEqual(module.module_id, updated.module_id)
        self.assertEqual("Variables Practical", updated.assessment_name)
        self.assertEqual(Decimal("75.50"), updated.max_mark)
        self.assertEqual(Decimal("25"), updated.weight)
        self.assertEqual(Decimal("50"), updated.pass_mark)

    def test_update_missing_assessment_returns_none(self):
        result = self.repository.update(
            999,
            "Missing",
            "quiz",
            Decimal("10"),
            None,
            None,
            ASSESSMENT_ACTIVE_STATUS,
        )

        self.assertIsNone(result)

    def test_deactivate_and_reactivate_keep_same_physical_record(self):
        course = self._create_course()
        assessment = self.repository.create(
            course.course_id,
            None,
            "Final Exam",
            "exam",
            Decimal("100"),
        )

        archived = self.repository.deactivate(assessment.assessment_id)
        active_again = self.repository.reactivate(assessment.assessment_id)

        self.assertEqual(assessment.assessment_id, archived.assessment_id)
        self.assertEqual(assessment.assessment_id, active_again.assessment_id)
        self.assertEqual(ASSESSMENT_ARCHIVED_STATUS, archived.status)
        self.assertEqual(ASSESSMENT_ACTIVE_STATUS, active_again.status)

    def test_foreign_key_constraints_are_friendly_errors(self):
        course = self._create_course()

        with self.assertRaisesRegex(RecordNotFoundError, "Course or module"):
            self.repository.create(
                999,
                None,
                "Missing Course Exam",
                "exam",
                Decimal("100"),
            )

        with self.assertRaisesRegex(RecordNotFoundError, "Course or module"):
            self.repository.create(
                course.course_id,
                999,
                "Missing Module Exam",
                "exam",
                Decimal("100"),
            )

    def test_schema_does_not_define_assessment_name_uniqueness(self):
        course = self._create_course()

        first = self.repository.create(
            course.course_id,
            None,
            "Final Exam",
            "exam",
            Decimal("100"),
        )
        second = self.repository.create(
            course.course_id,
            None,
            "Final Exam",
            "exam",
            Decimal("100"),
        )

        self.assertNotEqual(first.assessment_id, second.assessment_id)


if __name__ == "__main__":
    unittest.main()
