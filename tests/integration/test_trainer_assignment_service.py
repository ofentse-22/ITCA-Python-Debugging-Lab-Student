"""Integration tests for trainer assignment service behavior."""

import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.course import (
    COURSE_ACTIVE_STATUS,
    COURSE_PLANNED_STATUS,
)
from itca_training_centre.models.trainer_assignment import (
    ASSIGNMENT_ACTIVE_STATUS,
    ASSIGNMENT_ENDED_STATUS,
)
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.trainer_assignment_service import TrainerAssignmentService
from itca_training_centre.services.trainer_service import TrainerService
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from tests.helpers import temporary_database_path


class TrainerAssignmentServiceTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.trainer_service = TrainerService(self.database_path)
        self.course_service = CourseService(self.database_path)
        self.service = TrainerAssignmentService(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def _create_trainer(self, trainer_number="TRN-1001", first_name="Thandi", last_name="Dlamini"):
        return self.trainer_service.register_trainer(
            trainer_number,
            first_name,
            last_name,
        )

    def _create_course(self, course_code="PYF101", status=COURSE_ACTIVE_STATUS):
        return self.course_service.create_course(
            course_code,
            f"{course_code} Course",
            fee_amount="0",
            status=status,
        )

    def test_active_trainer_can_be_assigned_to_active_course(self):
        trainer = self._create_trainer()
        course = self._create_course()

        assignment = self.service.assign_trainer(
            trainer_number=" trn-1001 ",
            course_code=" pyf101 ",
            assigned_from="2026-09-01",
        )

        self.assertEqual(trainer.trainer_id, assignment.trainer_id)
        self.assertEqual(course.course_id, assignment.course_id)
        self.assertEqual("2026-09-01", assignment.assigned_from)
        self.assertEqual(ASSIGNMENT_ACTIVE_STATUS, assignment.status)

    def test_missing_trainer_or_course_is_reported(self):
        self._create_trainer()
        self._create_course()

        with self.assertRaisesRegex(RecordNotFoundError, "No trainer"):
            self.service.assign_trainer("TRN-9999", "PYF101", "2026-09-01")
        with self.assertRaisesRegex(RecordNotFoundError, "No course"):
            self.service.assign_trainer("TRN-1001", "MISSING", "2026-09-01")

    def test_trainer_and_course_must_be_active_for_new_assignments(self):
        self._create_trainer()
        self._create_course()
        self.trainer_service.deactivate_trainer("TRN-1001")

        with self.assertRaisesRegex(ValidationError, "Trainer must be active"):
            self.service.assign_trainer("TRN-1001", "PYF101", "2026-09-01")

        self._create_trainer("TRN-1002", "Ayesha", "Banda")
        self._create_course("SQL101", status=COURSE_PLANNED_STATUS)

        with self.assertRaisesRegex(ValidationError, "Course must be active"):
            self.service.assign_trainer("TRN-1002", "SQL101", "2026-09-01")

    def test_duplicate_active_assignment_is_rejected(self):
        self._create_trainer()
        self._create_course()
        self.service.assign_trainer("TRN-1001", "PYF101", "2026-09-01")

        with self.assertRaisesRegex(DuplicateRecordError, "actively assigned"):
            self.service.assign_trainer("TRN-1001", "PYF101", "2026-09-02")

    def test_listing_filters_by_trainer_course_and_status(self):
        self._create_trainer("TRN-1001", "Thandi", "Dlamini")
        self._create_trainer("TRN-1002", "Ayesha", "Banda")
        self._create_course("PYF101")
        self._create_course("SQL101")
        first = self.service.assign_trainer("TRN-1001", "SQL101", "2026-09-03")
        second = self.service.assign_trainer("TRN-1002", "PYF101", "2026-09-02")
        third = self.service.assign_trainer("TRN-1001", "PYF101", "2026-09-01")

        self.assertEqual(
            [second.assignment_id, third.assignment_id, first.assignment_id],
            [item.assignment_id for item in self.service.list_assignments()],
        )
        self.assertEqual(
            [third.assignment_id, first.assignment_id],
            [item.assignment_id for item in self.service.list_trainer_assignments("TRN-1001")],
        )
        self.assertEqual(
            [second.assignment_id, third.assignment_id],
            [item.assignment_id for item in self.service.list_course_assignments("PYF101")],
        )
        self.assertEqual(
            [third.assignment_id],
            [
                item.assignment_id
                for item in self.service.list_filtered_assignments(
                    trainer_number="TRN-1001",
                    course_code="PYF101",
                    status=ASSIGNMENT_ACTIVE_STATUS,
                )
            ],
        )

    def test_end_preserves_history_and_allows_later_active_assignment(self):
        self._create_trainer()
        self._create_course()
        original = self.service.assign_trainer("TRN-1001", "PYF101", "2026-09-01")

        ended = self.service.end_assignment("TRN-1001", "PYF101", "2026-09-30")
        new_active = self.service.assign_trainer("TRN-1001", "PYF101", "2026-10-01")

        self.assertEqual(original.assignment_id, ended.assignment_id)
        self.assertEqual(ASSIGNMENT_ENDED_STATUS, ended.status)
        self.assertEqual("2026-09-30", ended.assigned_to)
        self.assertNotEqual(original.assignment_id, new_active.assignment_id)
        self.assertEqual(
            [new_active.assignment_id],
            [item.assignment_id for item in self.service.list_trainer_assignments("TRN-1001")],
        )
        self.assertEqual(
            [original.assignment_id, new_active.assignment_id],
            [
                item.assignment_id
                for item in self.service.list_trainer_assignments(
                    "TRN-1001",
                    include_ended=True,
                )
            ],
        )

    def test_reactivate_latest_ended_assignment_uses_same_record(self):
        self._create_trainer()
        self._create_course()
        original = self.service.assign_trainer("TRN-1001", "PYF101", "2026-09-01")
        self.service.end_assignment("TRN-1001", "PYF101", "2026-09-30")

        active_again = self.service.reactivate_assignment("TRN-1001", "PYF101")
        second_reactivation = self.service.reactivate_assignment("TRN-1001", "PYF101")

        self.assertEqual(original.assignment_id, active_again.assignment_id)
        self.assertEqual(original.assignment_id, second_reactivation.assignment_id)
        self.assertEqual(ASSIGNMENT_ACTIVE_STATUS, active_again.status)
        self.assertIsNone(active_again.assigned_to)

    def test_reactivate_requires_active_parents(self):
        self._create_trainer()
        self._create_course()
        self.service.assign_trainer("TRN-1001", "PYF101", "2026-09-01")
        self.service.end_assignment("TRN-1001", "PYF101", "2026-09-30")
        self.trainer_service.deactivate_trainer("TRN-1001")

        with self.assertRaisesRegex(ValidationError, "Trainer must be active"):
            self.service.reactivate_assignment("TRN-1001", "PYF101")

    def test_end_without_active_assignment_reports_not_found(self):
        self._create_trainer()
        self._create_course()

        with self.assertRaisesRegex(RecordNotFoundError, "No active assignment"):
            self.service.end_assignment("TRN-1001", "PYF101")

    def test_invalid_dates_and_status_are_rejected(self):
        self._create_trainer()
        self._create_course()

        with self.assertRaisesRegex(ValidationError, "Assigned from"):
            self.service.assign_trainer("TRN-1001", "PYF101", "09/01/2026")
        self.service.assign_trainer("TRN-1001", "PYF101", "2026-09-01")
        with self.assertRaisesRegex(ValidationError, "before assigned from date"):
            self.service.end_assignment("TRN-1001", "PYF101", "2026-08-31")
        with self.assertRaisesRegex(ValidationError, "Assigned to"):
            self.service.end_assignment("TRN-1001", "PYF101", "2026/09/30")
        with self.assertRaisesRegex(ValidationError, "Assignment status"):
            self.service.list_assignments(status="paused")

        active = self.service.list_trainer_assignments("TRN-1001")
        self.assertEqual([ASSIGNMENT_ACTIVE_STATUS], [item.status for item in active])


if __name__ == "__main__":
    unittest.main()
