"""Integration tests for the trainer repository."""

import unittest

from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.trainer import (
    TRAINER_ACTIVE_STATUS,
    TRAINER_INACTIVE_STATUS,
)
from itca_training_centre.repositories.trainer_repository import TrainerRepository
from itca_training_centre.utils.exceptions import DuplicateRecordError
from tests.helpers import temporary_database_path


class TrainerRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.repository = TrainerRepository(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_create_trainer_round_trips_fields(self):
        trainer = self.repository.create(
            trainer_number="TRN-1001",
            first_name="Thandi",
            last_name="Dlamini",
            email="thandi@example.edu",
            phone="555-1001",
        )

        self.assertIsInstance(trainer.trainer_id, int)
        self.assertEqual("TRN-1001", trainer.trainer_number)
        self.assertEqual("Thandi", trainer.first_name)
        self.assertEqual("Dlamini", trainer.last_name)
        self.assertEqual("thandi@example.edu", trainer.email)
        self.assertEqual("555-1001", trainer.phone)
        self.assertEqual(TRAINER_ACTIVE_STATUS, trainer.status)
        self.assertTrue(trainer.created_at.endswith("Z"))
        self.assertTrue(trainer.updated_at.endswith("Z"))

    def test_get_existing_trainer_by_id_and_number(self):
        created = self.repository.create("TRN-1001", "Thandi", "Dlamini", None, None)

        by_id = self.repository.get_by_id(created.trainer_id)
        by_number = self.repository.get_by_number("TRN-1001")

        self.assertEqual(created, by_id)
        self.assertEqual(created, by_number)

    def test_missing_trainer_returns_none(self):
        self.assertIsNone(self.repository.get_by_id(999))
        self.assertIsNone(self.repository.get_by_number("MISSING"))

    def test_list_trainers_excludes_inactive_by_default(self):
        active = self.repository.create("TRN-1001", "Thandi", "Dlamini", None, None)
        inactive = self.repository.create("TRN-1002", "Ayesha", "Banda", None, None)
        self.repository.deactivate(inactive.trainer_id)

        active_trainers = self.repository.list_trainers()
        all_trainers = self.repository.list_trainers(include_inactive=True)

        self.assertEqual([active.trainer_number], [trainer.trainer_number for trainer in active_trainers])
        self.assertEqual(
            [inactive.trainer_number, active.trainer_number],
            [trainer.trainer_number for trainer in all_trainers],
        )

    def test_list_trainers_uses_deterministic_name_ordering(self):
        self.repository.create("TRN-1003", "Zanele", "Zulu", None, None)
        self.repository.create("TRN-1001", "Amina", "Banda", None, None)
        self.repository.create("TRN-1002", "Bongi", "Banda", None, None)

        trainers = self.repository.list_trainers()

        self.assertEqual(
            ["TRN-1001", "TRN-1002", "TRN-1003"],
            [trainer.trainer_number for trainer in trainers],
        )

    def test_search_finds_number_name_combined_name_and_email(self):
        self.repository.create(
            "TRN-1001",
            "Thandi",
            "Dlamini",
            "thandi@example.edu",
            None,
        )

        terms = ["TRN-1001", "Thandi", "Dlamini", "Thandi Dlamini", "example.edu"]
        for term in terms:
            with self.subTest(term=term):
                results = self.repository.search(term)
                self.assertEqual(["TRN-1001"], [trainer.trainer_number for trainer in results])

    def test_search_excludes_inactive_unless_requested(self):
        trainer = self.repository.create("TRN-1001", "Thandi", "Dlamini", None, None)
        self.repository.deactivate(trainer.trainer_id)

        self.assertEqual([], self.repository.search("Thandi"))
        self.assertEqual(
            ["TRN-1001"],
            [result.trainer_number for result in self.repository.search("Thandi", True)],
        )

    def test_update_mutable_fields_preserves_trainer_number(self):
        trainer = self.repository.create("TRN-1001", "Thandi", "Dlamini", None, None)

        updated = self.repository.update(
            trainer_id=trainer.trainer_id,
            first_name="Thando",
            last_name="Naidoo",
            email="thando@example.edu",
            phone="555-2002",
        )

        self.assertEqual(trainer.trainer_id, updated.trainer_id)
        self.assertEqual("TRN-1001", updated.trainer_number)
        self.assertEqual("Thando", updated.first_name)
        self.assertEqual("Naidoo", updated.last_name)
        self.assertEqual("thando@example.edu", updated.email)
        self.assertEqual("555-2002", updated.phone)

    def test_update_missing_trainer_returns_none(self):
        self.assertIsNone(
            self.repository.update(999, "Thandi", "Dlamini", None, None)
        )

    def test_deactivate_and_reactivate_keep_same_physical_record(self):
        trainer = self.repository.create("TRN-1001", "Thandi", "Dlamini", None, None)

        inactive = self.repository.deactivate(trainer.trainer_id)
        active_again = self.repository.reactivate(trainer.trainer_id)

        self.assertEqual(trainer.trainer_id, inactive.trainer_id)
        self.assertEqual(trainer.trainer_id, active_again.trainer_id)
        self.assertEqual(TRAINER_INACTIVE_STATUS, inactive.status)
        self.assertEqual(TRAINER_ACTIVE_STATUS, active_again.status)

    def test_duplicate_trainer_number_and_email_are_rejected(self):
        self.repository.create(
            "TRN-1001",
            "Thandi",
            "Dlamini",
            "thandi@example.edu",
            None,
        )

        with self.assertRaisesRegex(DuplicateRecordError, "Trainer number"):
            self.repository.create("TRN-1001", "Bongi", "Mokoena", None, None)
        with self.assertRaisesRegex(DuplicateRecordError, "Email address"):
            self.repository.create(
                "TRN-1002",
                "Bongi",
                "Mokoena",
                "thandi@example.edu",
                None,
            )


if __name__ == "__main__":
    unittest.main()
