"""Integration tests for the course repository."""

from decimal import Decimal
import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.course import (
    COURSE_ACTIVE_STATUS,
    COURSE_ARCHIVED_STATUS,
    COURSE_COMPLETED_STATUS,
    COURSE_PLANNED_STATUS,
)
from itca_training_centre.repositories.course_repository import CourseRepository
from itca_training_centre.utils.exceptions import DuplicateRecordError
from tests.helpers import temporary_database_path


class CourseRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.repository = CourseRepository(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_create_course_round_trips_fields(self):
        course = self.repository.create(
            course_code="PYF101",
            course_name="Python Fundamentals",
            description="Core Python skills",
            fee_amount=Decimal("1500.50"),
            status=COURSE_ACTIVE_STATUS,
        )

        self.assertIsInstance(course.course_id, int)
        self.assertEqual("PYF101", course.course_code)
        self.assertEqual("Python Fundamentals", course.course_name)
        self.assertEqual("Core Python skills", course.description)
        self.assertEqual(Decimal("1500.5"), course.fee_amount)
        self.assertEqual(COURSE_ACTIVE_STATUS, course.status)
        self.assertTrue(course.created_at.endswith("Z"))
        self.assertTrue(course.updated_at.endswith("Z"))

    def test_get_existing_course_by_id_and_code(self):
        created = self.repository.create(
            "PYF101",
            "Python Fundamentals",
            None,
            Decimal("0"),
            COURSE_PLANNED_STATUS,
        )

        by_id = self.repository.get_by_id(created.course_id)
        by_code = self.repository.get_by_code("PYF101")

        self.assertEqual(created, by_id)
        self.assertEqual(created, by_code)

    def test_missing_course_returns_none(self):
        self.assertIsNone(self.repository.get_by_id(999))
        self.assertIsNone(self.repository.get_by_code("MISSING"))

    def test_list_courses_excludes_archived_by_default(self):
        planned = self.repository.create(
            "PYF101",
            "Python Fundamentals",
            None,
            Decimal("0"),
            COURSE_PLANNED_STATUS,
        )
        active = self.repository.create(
            "SQL101",
            "SQLite Basics",
            None,
            Decimal("0"),
            COURSE_ACTIVE_STATUS,
        )
        archived = self.repository.create(
            "WEB101",
            "Web Foundations",
            None,
            Decimal("0"),
            COURSE_ARCHIVED_STATUS,
        )

        courses = self.repository.list_courses()

        self.assertEqual(
            [planned.course_code, active.course_code],
            [course.course_code for course in courses],
        )
        self.assertNotIn(archived.course_code, [course.course_code for course in courses])

    def test_list_courses_can_include_archived(self):
        self.repository.create("PYF101", "Python Fundamentals", None, Decimal("0"))
        self.repository.create(
            "WEB101",
            "Web Foundations",
            None,
            Decimal("0"),
            COURSE_ARCHIVED_STATUS,
        )

        courses = self.repository.list_courses(include_archived=True)

        self.assertEqual(
            ["PYF101", "WEB101"],
            [course.course_code for course in courses],
        )
        self.assertEqual(COURSE_ARCHIVED_STATUS, courses[1].status)

    def test_list_courses_can_filter_by_status(self):
        self.repository.create("PYF101", "Python Fundamentals", None, Decimal("0"))
        self.repository.create(
            "SQL101",
            "SQLite Basics",
            None,
            Decimal("0"),
            COURSE_COMPLETED_STATUS,
        )

        courses = self.repository.list_courses(status=COURSE_COMPLETED_STATUS)

        self.assertEqual(["SQL101"], [course.course_code for course in courses])

    def test_list_courses_uses_deterministic_course_code_ordering(self):
        self.repository.create("WEB101", "Web Foundations", None, Decimal("0"))
        self.repository.create("PYF101", "Python Fundamentals", None, Decimal("0"))
        self.repository.create("SQL101", "SQLite Basics", None, Decimal("0"))

        courses = self.repository.list_courses()

        self.assertEqual(
            ["PYF101", "SQL101", "WEB101"],
            [course.course_code for course in courses],
        )

    def test_search_finds_code_name_and_description(self):
        self.repository.create(
            "PYF101",
            "Python Fundamentals",
            "Variables, decisions, and loops",
            Decimal("0"),
        )

        terms = ["PYF101", "Python", "decisions"]
        for term in terms:
            with self.subTest(term=term):
                results = self.repository.search(term)
                self.assertEqual(["PYF101"], [course.course_code for course in results])

    def test_search_excludes_archived_unless_requested(self):
        self.repository.create(
            "PYF101",
            "Python Fundamentals",
            None,
            Decimal("0"),
            COURSE_ARCHIVED_STATUS,
        )

        self.assertEqual([], self.repository.search("Python"))
        self.assertEqual(
            ["PYF101"],
            [course.course_code for course in self.repository.search("Python", True)],
        )

    def test_search_returns_no_results_for_missing_text(self):
        self.repository.create("PYF101", "Python Fundamentals", None, Decimal("0"))

        self.assertEqual([], self.repository.search("Missing"))

    def test_update_mutable_fields_preserves_course_code(self):
        course = self.repository.create("PYF101", "Python Fundamentals", None, Decimal("0"))

        updated = self.repository.update(
            course_id=course.course_id,
            course_name="Python Essentials",
            description="Updated course",
            fee_amount=Decimal("1750.00"),
            status=COURSE_COMPLETED_STATUS,
        )

        self.assertEqual(course.course_id, updated.course_id)
        self.assertEqual("PYF101", updated.course_code)
        self.assertEqual("Python Essentials", updated.course_name)
        self.assertEqual("Updated course", updated.description)
        self.assertEqual(Decimal("1750"), updated.fee_amount)
        self.assertEqual(COURSE_COMPLETED_STATUS, updated.status)

    def test_update_missing_course_returns_none(self):
        result = self.repository.update(
            999,
            "Python Fundamentals",
            None,
            Decimal("0"),
            COURSE_ACTIVE_STATUS,
        )

        self.assertIsNone(result)

    def test_deactivate_and_reactivate_keep_same_physical_record(self):
        course = self.repository.create("PYF101", "Python Fundamentals", None, Decimal("0"))

        archived = self.repository.deactivate(course.course_id)
        active_again = self.repository.reactivate(course.course_id)

        self.assertEqual(course.course_id, archived.course_id)
        self.assertEqual(course.course_id, active_again.course_id)
        self.assertEqual(COURSE_ARCHIVED_STATUS, archived.status)
        self.assertEqual(COURSE_ACTIVE_STATUS, active_again.status)

    def test_duplicate_course_code_is_rejected(self):
        self.repository.create("PYF101", "Python Fundamentals", None, Decimal("0"))

        with self.assertRaisesRegex(DuplicateRecordError, "Course code"):
            self.repository.create("PYF101", "Python Essentials", None, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
