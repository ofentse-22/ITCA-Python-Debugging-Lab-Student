"""Integration tests for the module repository."""

from decimal import Decimal
import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.module import MODULE_ACTIVE_STATUS, MODULE_ARCHIVED_STATUS
from itca_training_centre.repositories.course_repository import CourseRepository
from itca_training_centre.repositories.module_repository import ModuleRepository
from itca_training_centre.utils.exceptions import DuplicateRecordError, RecordNotFoundError
from tests.helpers import temporary_database_path


class ModuleRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.course_repository = CourseRepository(self.database_path)
        self.module_repository = ModuleRepository(self.database_path)
        self.course = self.course_repository.create(
            "PYF101",
            "Python Fundamentals",
            None,
            Decimal("0"),
        )
        self.second_course = self.course_repository.create(
            "SQL101",
            "SQLite Basics",
            None,
            Decimal("0"),
        )

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_create_module_round_trips_fields(self):
        module = self.module_repository.create(
            course_id=self.course.course_id,
            module_code="MOD-101",
            module_name="Variables and Data Types",
            sequence_number=1,
        )

        self.assertIsInstance(module.module_id, int)
        self.assertEqual(self.course.course_id, module.course_id)
        self.assertEqual("MOD-101", module.module_code)
        self.assertEqual("Variables and Data Types", module.module_name)
        self.assertEqual(1, module.sequence_number)
        self.assertEqual(MODULE_ACTIVE_STATUS, module.status)

    def test_get_existing_module_by_id_and_course_code_pair(self):
        created = self.module_repository.create(
            self.course.course_id,
            "MOD-101",
            "Variables and Data Types",
            1,
        )

        by_id = self.module_repository.get_by_id(created.module_id)
        by_pair = self.module_repository.get_by_course_and_code(
            self.course.course_id,
            "MOD-101",
        )

        self.assertEqual(created, by_id)
        self.assertEqual(created, by_pair)

    def test_missing_module_returns_none(self):
        self.assertIsNone(self.module_repository.get_by_id(999))
        self.assertIsNone(
            self.module_repository.get_by_course_and_code(
                self.course.course_id,
                "MISSING",
            )
        )

    def test_create_for_missing_course_is_translated(self):
        with self.assertRaisesRegex(RecordNotFoundError, "Course"):
            self.module_repository.create(999, "MOD-101", "Variables", 1)

    def test_list_for_course_excludes_other_courses_and_orders_by_sequence(self):
        self.module_repository.create(self.course.course_id, "MOD-201", "Loops", 2)
        self.module_repository.create(self.course.course_id, "MOD-101", "Variables", 1)
        self.module_repository.create(self.second_course.course_id, "MOD-101", "SQL", 1)

        modules = self.module_repository.list_for_course(self.course.course_id)

        self.assertEqual(
            ["MOD-101", "MOD-201"],
            [module.module_code for module in modules],
        )
        self.assertTrue(all(module.course_id == self.course.course_id for module in modules))

    def test_list_for_course_can_include_archived(self):
        active = self.module_repository.create(self.course.course_id, "MOD-101", "Variables", 1)
        archived = self.module_repository.create(self.course.course_id, "MOD-201", "Loops", 2)
        self.module_repository.deactivate(archived.module_id)

        modules = self.module_repository.list_for_course(
            self.course.course_id,
            include_archived=True,
        )

        self.assertEqual(
            [active.module_code, archived.module_code],
            [module.module_code for module in modules],
        )
        self.assertEqual(MODULE_ARCHIVED_STATUS, modules[1].status)

    def test_search_finds_code_and_name(self):
        self.module_repository.create(self.course.course_id, "MOD-101", "Variables", 1)

        terms = ["MOD-101", "Variables"]
        for term in terms:
            with self.subTest(term=term):
                results = self.module_repository.search(term)
                self.assertEqual(["MOD-101"], [module.module_code for module in results])

    def test_search_can_be_filtered_to_one_course(self):
        self.module_repository.create(self.course.course_id, "MOD-101", "Variables", 1)
        self.module_repository.create(self.second_course.course_id, "MOD-101", "SQL", 1)

        results = self.module_repository.search(
            "MOD-101",
            course_id=self.second_course.course_id,
        )

        self.assertEqual([self.second_course.course_id], [module.course_id for module in results])

    def test_search_excludes_archived_unless_requested(self):
        module = self.module_repository.create(self.course.course_id, "MOD-101", "Variables", 1)
        self.module_repository.deactivate(module.module_id)

        self.assertEqual([], self.module_repository.search("Variables"))
        self.assertEqual(
            ["MOD-101"],
            [
                result.module_code
                for result in self.module_repository.search("Variables", include_archived=True)
            ],
        )

    def test_search_returns_no_results_for_missing_text(self):
        self.module_repository.create(self.course.course_id, "MOD-101", "Variables", 1)

        self.assertEqual([], self.module_repository.search("Missing"))

    def test_update_mutable_fields_preserves_course_and_module_code(self):
        module = self.module_repository.create(self.course.course_id, "MOD-101", "Variables", 1)

        updated = self.module_repository.update(
            module_id=module.module_id,
            module_name="Variables, Types, and Operators",
            sequence_number=2,
            status=MODULE_ARCHIVED_STATUS,
        )

        self.assertEqual(module.module_id, updated.module_id)
        self.assertEqual(self.course.course_id, updated.course_id)
        self.assertEqual("MOD-101", updated.module_code)
        self.assertEqual("Variables, Types, and Operators", updated.module_name)
        self.assertEqual(2, updated.sequence_number)
        self.assertEqual(MODULE_ARCHIVED_STATUS, updated.status)

    def test_update_missing_module_returns_none(self):
        result = self.module_repository.update(999, "Variables", 1, MODULE_ACTIVE_STATUS)

        self.assertIsNone(result)

    def test_duplicate_module_code_is_rejected_only_within_same_course(self):
        self.module_repository.create(self.course.course_id, "MOD-101", "Variables", 1)

        same_code_other_course = self.module_repository.create(
            self.second_course.course_id,
            "MOD-101",
            "Relational Tables",
            1,
        )

        self.assertEqual(self.second_course.course_id, same_code_other_course.course_id)
        with self.assertRaisesRegex(DuplicateRecordError, "Module code"):
            self.module_repository.create(self.course.course_id, "MOD-101", "Loops", 2)

    def test_duplicate_sequence_is_rejected_within_same_course(self):
        self.module_repository.create(self.course.course_id, "MOD-101", "Variables", 1)

        with self.assertRaisesRegex(DuplicateRecordError, "sequence"):
            self.module_repository.create(self.course.course_id, "MOD-201", "Loops", 1)

    def test_deactivate_and_reactivate_keep_same_physical_record(self):
        module = self.module_repository.create(self.course.course_id, "MOD-101", "Variables", 1)

        archived = self.module_repository.deactivate(module.module_id)
        active_again = self.module_repository.reactivate(module.module_id)

        self.assertEqual(module.module_id, archived.module_id)
        self.assertEqual(module.module_id, active_again.module_id)
        self.assertEqual(MODULE_ARCHIVED_STATUS, archived.status)
        self.assertEqual(MODULE_ACTIVE_STATUS, active_again.status)


if __name__ == "__main__":
    unittest.main()
