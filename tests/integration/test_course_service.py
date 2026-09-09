"""Integration tests for course service business behavior."""

from decimal import Decimal
import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.course import (
    COURSE_ACTIVE_STATUS,
    COURSE_ARCHIVED_STATUS,
    COURSE_COMPLETED_STATUS,
    COURSE_PLANNED_STATUS,
)
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from tests.helpers import temporary_database_path


class CourseServiceTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.service = CourseService(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_valid_creation_normalizes_values(self):
        course = self.service.create_course(
            course_code=" pyf101 ",
            course_name="  Python   Fundamentals ",
            description="  Core   skills ",
            fee_amount="1500.50",
            status=" active ",
        )

        self.assertEqual("PYF101", course.course_code)
        self.assertEqual("Python Fundamentals", course.course_name)
        self.assertEqual("Core skills", course.description)
        self.assertEqual(Decimal("1500.5"), course.fee_amount)
        self.assertEqual(COURSE_ACTIVE_STATUS, course.status)

    def test_creation_defaults_to_planned_and_zero_fee(self):
        course = self.service.create_course("PYF101", "Python Fundamentals")

        self.assertEqual(Decimal("0"), course.fee_amount)
        self.assertEqual(COURSE_PLANNED_STATUS, course.status)

    def test_blank_required_fields_are_rejected(self):
        cases = [
            {"course_code": "", "course_name": "Python Fundamentals"},
            {"course_code": "PYF101", "course_name": " "},
        ]

        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValidationError):
                    self.service.create_course(**kwargs)

    def test_invalid_fee_is_rejected(self):
        for fee_amount in ("not-money", "-1"):
            with self.subTest(fee_amount=fee_amount):
                with self.assertRaises(ValidationError):
                    self.service.create_course(
                        "PYF101",
                        "Python Fundamentals",
                        fee_amount=fee_amount,
                    )

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.service.create_course("PYF101", "Python Fundamentals", status="draft")

    def test_duplicate_course_code_is_translated(self):
        self.service.create_course("PYF101", "Python Fundamentals")

        with self.assertRaisesRegex(DuplicateRecordError, "Course code"):
            self.service.create_course(" pyf101 ", "Python Essentials")

    def test_get_missing_course_raises_not_found(self):
        with self.assertRaisesRegex(RecordNotFoundError, "PYF999"):
            self.service.get_course_by_code("pyf999")

    def test_search_normalizes_query(self):
        self.service.create_course("PYF101", "Python Fundamentals")

        results = self.service.search_courses("  python  ")

        self.assertEqual(["PYF101"], [course.course_code for course in results])

    def test_update_course_changes_mutable_fields(self):
        self.service.create_course("PYF101", "Python Fundamentals")

        updated = self.service.update_course(
            course_code="PYF101",
            course_name="Python Essentials",
            description="Updated description",
            fee_amount="1750.00",
            status=COURSE_COMPLETED_STATUS,
        )

        self.assertEqual("PYF101", updated.course_code)
        self.assertEqual("Python Essentials", updated.course_name)
        self.assertEqual("Updated description", updated.description)
        self.assertEqual(Decimal("1750"), updated.fee_amount)
        self.assertEqual(COURSE_COMPLETED_STATUS, updated.status)

    def test_update_course_preserves_fee_when_not_supplied(self):
        self.service.create_course("PYF101", "Python Fundamentals", fee_amount="1500")

        updated = self.service.update_course(
            course_code="PYF101",
            course_name="Python Essentials",
        )

        self.assertEqual(Decimal("1500"), updated.fee_amount)

    def test_invalid_update_is_rejected(self):
        self.service.create_course("PYF101", "Python Fundamentals")

        with self.assertRaises(ValidationError):
            self.service.update_course(
                course_code="PYF101",
                course_name="",
                fee_amount="0",
            )

    def test_deactivate_and_reactivate_keep_same_record(self):
        created = self.service.create_course("PYF101", "Python Fundamentals")

        archived = self.service.deactivate_course("PYF101")
        active_again = self.service.reactivate_course("PYF101")

        self.assertEqual(created.course_id, archived.course_id)
        self.assertEqual(created.course_id, active_again.course_id)
        self.assertEqual(COURSE_ARCHIVED_STATUS, archived.status)
        self.assertEqual(COURSE_ACTIVE_STATUS, active_again.status)

    def test_default_listing_excludes_archived_courses(self):
        self.service.create_course("PYF101", "Python Fundamentals")
        self.service.create_course("SQL101", "SQLite Basics")
        self.service.deactivate_course("SQL101")

        active_courses = self.service.list_courses()
        all_courses = self.service.list_courses(include_archived=True)

        self.assertEqual(["PYF101"], [course.course_code for course in active_courses])
        self.assertEqual(["PYF101", "SQL101"], [course.course_code for course in all_courses])


if __name__ == "__main__":
    unittest.main()
