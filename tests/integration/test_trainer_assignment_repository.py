"""Integration tests for the trainer assignment repository."""

from decimal import Decimal
import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.course import COURSE_ACTIVE_STATUS
from itca_training_centre.models.trainer_assignment import (
    ASSIGNMENT_ACTIVE_STATUS,
    ASSIGNMENT_ENDED_STATUS,
)
from itca_training_centre.repositories.course_repository import CourseRepository
from itca_training_centre.repositories.trainer_assignment_repository import (
    TrainerAssignmentRepository,
)
from itca_training_centre.repositories.trainer_repository import TrainerRepository
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
)
from tests.helpers import temporary_database_path


class TrainerAssignmentRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.trainer_repository = TrainerRepository(self.database_path)
        self.course_repository = CourseRepository(self.database_path)
        self.repository = TrainerAssignmentRepository(self.database_path)
        self.trainer_a = self.trainer_repository.create(
            "TRN-1001",
            "Thandi",
            "Dlamini",
            None,
            None,
        )
        self.trainer_b = self.trainer_repository.create(
            "TRN-1002",
            "Ayesha",
            "Banda",
            None,
            None,
        )
        self.course_a = self.course_repository.create(
            "PYF101",
            "Python Fundamentals",
            None,
            Decimal("0"),
            COURSE_ACTIVE_STATUS,
        )
        self.course_b = self.course_repository.create(
            "SQL101",
            "SQLite Basics",
            None,
            Decimal("0"),
            COURSE_ACTIVE_STATUS,
        )

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_create_assignment_round_trips_fields(self):
        assignment = self.repository.create(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
            "2026-09-01",
        )

        self.assertIsInstance(assignment.assignment_id, int)
        self.assertEqual(self.trainer_a.trainer_id, assignment.trainer_id)
        self.assertEqual(self.course_a.course_id, assignment.course_id)
        self.assertEqual("2026-09-01", assignment.assigned_from)
        self.assertIsNone(assignment.assigned_to)
        self.assertEqual(ASSIGNMENT_ACTIVE_STATUS, assignment.status)

    def test_get_existing_assignment_by_id_active_pair_and_latest_pair(self):
        created = self.repository.create(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
            "2026-09-01",
        )

        by_id = self.repository.get_by_id(created.assignment_id)
        by_active_pair = self.repository.get_active_for_trainer_course(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
        )
        by_latest_pair = self.repository.get_latest_for_trainer_course(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
        )

        self.assertEqual(created, by_id)
        self.assertEqual(created, by_active_pair)
        self.assertEqual(created, by_latest_pair)

    def test_missing_assignment_returns_none(self):
        self.assertIsNone(self.repository.get_by_id(999))
        self.assertIsNone(
            self.repository.get_active_for_trainer_course(
                self.trainer_a.trainer_id,
                self.course_a.course_id,
            )
        )

    def test_list_methods_filter_and_order_relationships(self):
        first = self.repository.create(
            self.trainer_a.trainer_id,
            self.course_b.course_id,
            "2026-09-03",
        )
        second = self.repository.create(
            self.trainer_b.trainer_id,
            self.course_a.course_id,
            "2026-09-02",
        )
        third = self.repository.create(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
            "2026-09-01",
        )

        all_assignments = self.repository.list_assignments()
        trainer_assignments = self.repository.list_for_trainer(self.trainer_a.trainer_id)
        course_assignments = self.repository.list_for_course(self.course_a.course_id)
        pair_assignments = self.repository.list_for_trainer_course(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
        )

        self.assertEqual(
            [second.assignment_id, third.assignment_id, first.assignment_id],
            [assignment.assignment_id for assignment in all_assignments],
        )
        self.assertEqual(
            [third.assignment_id, first.assignment_id],
            [assignment.assignment_id for assignment in trainer_assignments],
        )
        self.assertEqual(
            [second.assignment_id, third.assignment_id],
            [assignment.assignment_id for assignment in course_assignments],
        )
        self.assertEqual([third.assignment_id], [item.assignment_id for item in pair_assignments])

    def test_ended_assignments_are_excluded_by_default(self):
        assignment = self.repository.create(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
            "2026-09-01",
        )
        ended = self.repository.end(assignment.assignment_id, "2026-09-30")

        active_results = self.repository.list_for_trainer(self.trainer_a.trainer_id)
        historical_results = self.repository.list_for_trainer(
            self.trainer_a.trainer_id,
            include_ended=True,
        )

        self.assertEqual(ASSIGNMENT_ENDED_STATUS, ended.status)
        self.assertEqual("2026-09-30", ended.assigned_to)
        self.assertEqual([], active_results)
        self.assertEqual(
            [assignment.assignment_id],
            [item.assignment_id for item in historical_results],
        )

    def test_duplicate_active_assignment_is_rejected_but_new_active_after_end_is_allowed(self):
        original = self.repository.create(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
            "2026-09-01",
        )

        with self.assertRaisesRegex(DuplicateRecordError, "actively assigned"):
            self.repository.create(
                self.trainer_a.trainer_id,
                self.course_a.course_id,
                "2026-09-02",
            )

        self.repository.end(original.assignment_id, "2026-09-30")
        new_active = self.repository.create(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
            "2026-10-01",
        )

        self.assertNotEqual(original.assignment_id, new_active.assignment_id)
        self.assertEqual(
            new_active.assignment_id,
            self.repository.get_active_for_trainer_course(
                self.trainer_a.trainer_id,
                self.course_a.course_id,
            ).assignment_id,
        )

    def test_reactivate_ended_assignment_uses_same_physical_record(self):
        assignment = self.repository.create(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
            "2026-09-01",
        )
        self.repository.end(assignment.assignment_id, "2026-09-30")

        reactivated = self.repository.reactivate(assignment.assignment_id)

        self.assertEqual(assignment.assignment_id, reactivated.assignment_id)
        self.assertEqual(ASSIGNMENT_ACTIVE_STATUS, reactivated.status)
        self.assertIsNone(reactivated.assigned_to)

    def test_reactivating_when_active_pair_exists_is_rejected(self):
        old_assignment = self.repository.create(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
            "2026-09-01",
        )
        self.repository.end(old_assignment.assignment_id, "2026-09-30")
        self.repository.create(
            self.trainer_a.trainer_id,
            self.course_a.course_id,
            "2026-10-01",
        )

        with self.assertRaisesRegex(DuplicateRecordError, "actively assigned"):
            self.repository.reactivate(old_assignment.assignment_id)

    def test_end_missing_assignment_returns_none(self):
        self.assertIsNone(self.repository.end(999, "2026-09-30"))

    def test_create_for_missing_trainer_or_course_is_translated(self):
        with self.assertRaisesRegex(RecordNotFoundError, "Trainer or course"):
            self.repository.create(999, self.course_a.course_id, "2026-09-01")
        with self.assertRaisesRegex(RecordNotFoundError, "Trainer or course"):
            self.repository.create(self.trainer_a.trainer_id, 999, "2026-09-01")


if __name__ == "__main__":
    unittest.main()
