"""Tests for the Trainer domain model."""

import unittest

from itca_training_centre.models.trainer import (
    TRAINER_ACTIVE_STATUS,
    TRAINER_ARCHIVED_STATUS,
    TRAINER_INACTIVE_STATUS,
    TRAINER_STATUSES,
    Trainer,
)


class TrainerModelTests(unittest.TestCase):
    def test_trainer_exposes_display_name_and_active_state(self):
        trainer = Trainer(
            trainer_id=1,
            trainer_number="TRN-1001",
            first_name="Thandi",
            last_name="Dlamini",
            email="thandi@example.edu",
            phone="555-1001",
            status=TRAINER_ACTIVE_STATUS,
            created_at="2026-01-01T00:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
        )

        self.assertEqual("Thandi Dlamini", trainer.full_name)
        self.assertTrue(trainer.is_active)
        self.assertFalse(trainer.is_inactive)

    def test_inactive_or_archived_trainer_is_not_active(self):
        for status in (TRAINER_INACTIVE_STATUS, TRAINER_ARCHIVED_STATUS):
            with self.subTest(status=status):
                trainer = Trainer(
                    trainer_id=1,
                    trainer_number="TRN-1001",
                    first_name="Thandi",
                    last_name="Dlamini",
                    email=None,
                    phone=None,
                    status=status,
                    created_at="2026-01-01T00:00:00.000Z",
                    updated_at="2026-01-01T00:00:00.000Z",
                )

                self.assertFalse(trainer.is_active)
                self.assertTrue(trainer.is_inactive)

    def test_status_constants_match_schema_values(self):
        self.assertEqual(("active", "inactive", "archived"), TRAINER_STATUSES)
        self.assertEqual("active", TRAINER_ACTIVE_STATUS)
        self.assertEqual("inactive", TRAINER_INACTIVE_STATUS)
        self.assertEqual("archived", TRAINER_ARCHIVED_STATUS)


if __name__ == "__main__":
    unittest.main()
