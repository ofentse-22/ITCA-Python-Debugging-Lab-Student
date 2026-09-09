"""Tests for the Module domain model."""

import unittest

from itca_training_centre.models.module import (
    MODULE_ACTIVE_STATUS,
    MODULE_ARCHIVED_STATUS,
    MODULE_STATUSES,
    Module,
)


class ModuleModelTests(unittest.TestCase):
    def test_module_exposes_active_and_archived_state(self):
        module = Module(
            module_id=1,
            course_id=10,
            module_code="MOD-101",
            module_name="Variables and Data Types",
            sequence_number=1,
            status=MODULE_ACTIVE_STATUS,
        )

        self.assertTrue(module.is_active)
        self.assertFalse(module.is_archived)

    def test_archived_module_is_not_active(self):
        module = Module(
            module_id=1,
            course_id=10,
            module_code="MOD-101",
            module_name="Variables and Data Types",
            sequence_number=1,
            status=MODULE_ARCHIVED_STATUS,
        )

        self.assertFalse(module.is_active)
        self.assertTrue(module.is_archived)

    def test_status_constants_match_schema_values(self):
        self.assertEqual(("active", "archived"), MODULE_STATUSES)


if __name__ == "__main__":
    unittest.main()
