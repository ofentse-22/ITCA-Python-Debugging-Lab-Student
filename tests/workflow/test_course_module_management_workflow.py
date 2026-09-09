"""End-to-end Course and Module Management workflow tests."""

import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.course import COURSE_ACTIVE_STATUS, COURSE_ARCHIVED_STATUS
from itca_training_centre.models.module import MODULE_ACTIVE_STATUS, MODULE_ARCHIVED_STATUS
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.module_service import ModuleService
from itca_training_centre.utils.exceptions import DuplicateRecordError
from tests.helpers import temporary_database_path


class CourseModuleManagementWorkflowTests(unittest.TestCase):
    def test_course_and_module_workflow_preserves_relationships_and_ids(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)
            course_service = CourseService(database_path)
            module_service = ModuleService(database_path)

            course_a = course_service.create_course(
                "PYF101",
                "Python Fundamentals",
                fee_amount="1500",
                status=COURSE_ACTIVE_STATUS,
            )
            course_b = course_service.create_course(
                "SQL101",
                "SQLite Basics",
                fee_amount="1200",
                status=COURSE_ACTIVE_STATUS,
            )
            module_a = module_service.create_module("PYF101", "MOD-101", "Variables", 1)
            module_b = module_service.create_module("SQL101", "MOD-101", "Tables", 1)

            with self.assertRaisesRegex(DuplicateRecordError, "Module code"):
                module_service.create_module("PYF101", "MOD-101", "Loops", 2)

            retrieved_course = course_service.get_course_by_code("PYF101")
            course_a_modules = module_service.list_modules_for_course("PYF101")
            updated_course = course_service.update_course(
                "PYF101",
                "Python Essentials",
                fee_amount="1750",
                status=COURSE_ACTIVE_STATUS,
            )
            updated_module = module_service.update_module(
                "PYF101",
                "MOD-101",
                "Variables and Operators",
                2,
                status=MODULE_ACTIVE_STATUS,
            )
            archived_course = course_service.deactivate_course("PYF101")
            active_course = course_service.reactivate_course("PYF101")
            archived_module = module_service.deactivate_module("PYF101", "MOD-101")
            active_module = module_service.reactivate_module("PYF101", "MOD-101")

            with open_database(database_path) as connection:
                course_count = connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
                module_count = connection.execute("SELECT COUNT(*) FROM modules").fetchone()[0]

        self.assertEqual(course_a.course_id, retrieved_course.course_id)
        self.assertEqual([module_a.module_id], [module.module_id for module in course_a_modules])
        self.assertEqual(course_a.course_id, updated_course.course_id)
        self.assertEqual("PYF101", updated_course.course_code)
        self.assertEqual("Python Essentials", updated_course.course_name)
        self.assertEqual(module_a.module_id, updated_module.module_id)
        self.assertEqual(course_a.course_id, updated_module.course_id)
        self.assertEqual("MOD-101", updated_module.module_code)
        self.assertEqual("Variables and Operators", updated_module.module_name)
        self.assertEqual(course_a.course_id, archived_course.course_id)
        self.assertEqual(course_a.course_id, active_course.course_id)
        self.assertEqual(COURSE_ARCHIVED_STATUS, archived_course.status)
        self.assertEqual(COURSE_ACTIVE_STATUS, active_course.status)
        self.assertEqual(module_a.module_id, archived_module.module_id)
        self.assertEqual(module_a.module_id, active_module.module_id)
        self.assertEqual(MODULE_ARCHIVED_STATUS, archived_module.status)
        self.assertEqual(MODULE_ACTIVE_STATUS, active_module.status)
        self.assertEqual(course_b.course_id, module_b.course_id)
        self.assertEqual(2, course_count)
        self.assertEqual(2, module_count)


if __name__ == "__main__":
    unittest.main()
