"""Tests for the TrainerAssignment domain model."""

import unittest

from itca_training_centre.models.trainer_assignment import (
    ASSIGNMENT_ACTIVE_STATUS,
    ASSIGNMENT_ENDED_STATUS,
    ASSIGNMENT_STATUSES,
    TrainerAssignment,
)


class TrainerAssignmentModelTests(unittest.TestCase):
    def test_active_assignment_state(self):
        assignment = TrainerAssignment(
            assignment_id=1,
            trainer_id=10,
            course_id=20,
            assigned_from="2026-09-01",
            assigned_to=None,
            status=ASSIGNMENT_ACTIVE_STATUS,
        )

        self.assertTrue(assignment.is_active)
        self.assertFalse(assignment.is_ended)

    def test_ended_assignment_state(self):
        assignment = TrainerAssignment(
            assignment_id=1,
            trainer_id=10,
            course_id=20,
            assigned_from="2026-09-01",
            assigned_to="2026-09-30",
            status=ASSIGNMENT_ENDED_STATUS,
        )

        self.assertFalse(assignment.is_active)
        self.assertTrue(assignment.is_ended)

    def test_status_constants_match_schema_values(self):
        self.assertEqual(("active", "ended"), ASSIGNMENT_STATUSES)
        self.assertEqual("active", ASSIGNMENT_ACTIVE_STATUS)
        self.assertEqual("ended", ASSIGNMENT_ENDED_STATUS)


if __name__ == "__main__":
    unittest.main()
