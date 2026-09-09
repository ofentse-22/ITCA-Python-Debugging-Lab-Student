"""Integration tests for module service business behavior."""

import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.module import MODULE_ACTIVE_STATUS, MODULE_ARCHIVED_STATUS
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.module_service import ModuleService
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from tests.helpers import temporary_database_path


class ModuleServiceTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.course_service = CourseService(self.database_path)
        self.module_service = ModuleService(self.database_path)
        self.course_service.create_course("PYF101", "Python Fundamentals")
        self.course_service.create_course("SQL101", "SQLite Basics")

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_valid_module_creation_normalizes_values(self):
        module = self.module_service.create_module(
            course_code=" pyf101 ",
            module_code=" mod-101 ",
            module_name="  Variables   and Types ",
            sequence_number=" 1 ",
            status=" active ",
        )

        self.assertEqual("MOD-101", module.module_code)
        self.assertEqual("Variables and Types", module.module_name)
        self.assertEqual(1, module.sequence_number)
        self.assertEqual(MODULE_ACTIVE_STATUS, module.status)

    def test_create_module_for_missing_course_raises_not_found(self):
        with self.assertRaisesRegex(RecordNotFoundError, "MISSING"):
            self.module_service.create_module("MISSING", "MOD-101", "Variables", 1)

    def test_blank_required_fields_are_rejected(self):
        cases = [
            {"course_code": "", "module_code": "MOD-101", "module_name": "Variables", "sequence_number": 1},
            {"course_code": "PYF101", "module_code": "", "module_name": "Variables", "sequence_number": 1},
            {"course_code": "PYF101", "module_code": "MOD-101", "module_name": "", "sequence_number": 1},
            {"course_code": "PYF101", "module_code": "MOD-101", "module_name": "Variables", "sequence_number": ""},
        ]

        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValidationError):
                    self.module_service.create_module(**kwargs)

    def test_invalid_sequence_and_status_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.module_service.create_module("PYF101", "MOD-101", "Variables", 0)

        with self.assertRaises(ValidationError):
            self.module_service.create_module(
                "PYF101",
                "MOD-101",
                "Variables",
                1,
                status="inactive",
            )

    def test_duplicate_module_code_is_scoped_to_course(self):
        self.module_service.create_module("PYF101", "MOD-101", "Variables", 1)

        same_code_other_course = self.module_service.create_module(
            "SQL101",
            "MOD-101",
            "Relational Tables",
            1,
        )

        self.assertEqual("MOD-101", same_code_other_course.module_code)
        with self.assertRaisesRegex(DuplicateRecordError, "Module code"):
            self.module_service.create_module("PYF101", "mod-101", "Loops", 2)

    def test_duplicate_sequence_is_translated(self):
        self.module_service.create_module("PYF101", "MOD-101", "Variables", 1)

        with self.assertRaisesRegex(DuplicateRecordError, "sequence"):
            self.module_service.create_module("PYF101", "MOD-201", "Loops", 1)

    def test_get_missing_module_raises_not_found(self):
        with self.assertRaisesRegex(RecordNotFoundError, "MOD-999"):
            self.module_service.get_module("PYF101", "MOD-999")

    def test_list_modules_for_course_orders_by_sequence(self):
        self.module_service.create_module("PYF101", "MOD-201", "Loops", 2)
        self.module_service.create_module("PYF101", "MOD-101", "Variables", 1)
        self.module_service.create_module("SQL101", "MOD-101", "Relational Tables", 1)

        modules = self.module_service.list_modules_for_course("PYF101")

        self.assertEqual(["MOD-101", "MOD-201"], [module.module_code for module in modules])

    def test_search_modules_can_be_restricted_to_course(self):
        self.module_service.create_module("PYF101", "MOD-101", "Variables", 1)
        sql_module = self.module_service.create_module(
            "SQL101",
            "MOD-101",
            "Relational Tables",
            1,
        )

        results = self.module_service.search_modules("MOD-101", course_code="SQL101")

        self.assertEqual([sql_module.course_id], [module.course_id for module in results])

    def test_update_module_changes_mutable_fields(self):
        self.module_service.create_module("PYF101", "MOD-101", "Variables", 1)

        updated = self.module_service.update_module(
            course_code="PYF101",
            module_code="MOD-101",
            module_name="Variables, Types, and Operators",
            sequence_number=2,
            status=MODULE_ARCHIVED_STATUS,
        )

        self.assertEqual("MOD-101", updated.module_code)
        self.assertEqual("Variables, Types, and Operators", updated.module_name)
        self.assertEqual(2, updated.sequence_number)
        self.assertEqual(MODULE_ARCHIVED_STATUS, updated.status)

    def test_deactivate_and_reactivate_keep_same_record(self):
        created = self.module_service.create_module("PYF101", "MOD-101", "Variables", 1)

        archived = self.module_service.deactivate_module("PYF101", "MOD-101")
        active_again = self.module_service.reactivate_module("PYF101", "MOD-101")

        self.assertEqual(created.module_id, archived.module_id)
        self.assertEqual(created.module_id, active_again.module_id)
        self.assertEqual(MODULE_ARCHIVED_STATUS, archived.status)
        self.assertEqual(MODULE_ACTIVE_STATUS, active_again.status)

    def test_default_listing_excludes_archived_modules(self):
        self.module_service.create_module("PYF101", "MOD-101", "Variables", 1)
        self.module_service.create_module("PYF101", "MOD-201", "Loops", 2)
        self.module_service.deactivate_module("PYF101", "MOD-201")

        active_modules = self.module_service.list_modules_for_course("PYF101")
        all_modules = self.module_service.list_modules_for_course(
            "PYF101",
            include_archived=True,
        )

        self.assertEqual(["MOD-101"], [module.module_code for module in active_modules])
        self.assertEqual(["MOD-101", "MOD-201"], [module.module_code for module in all_modules])


if __name__ == "__main__":
    unittest.main()
