"""Integration tests for trainer service business behavior."""

import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.trainer import (
    TRAINER_ACTIVE_STATUS,
    TRAINER_INACTIVE_STATUS,
)
from itca_training_centre.services.trainer_service import TrainerService
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from tests.helpers import temporary_database_path


class TrainerServiceTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.service = TrainerService(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def test_valid_registration_normalizes_whitespace_identifier_and_email(self):
        trainer = self.service.register_trainer(
            trainer_number=" trn-1001 ",
            first_name="  Thandi  ",
            last_name="  Dlamini  ",
            email=" THANDI.EXAMPLE@EXAMPLE.EDU ",
            phone=" 555-1001 ",
        )

        self.assertEqual("TRN-1001", trainer.trainer_number)
        self.assertEqual("Thandi", trainer.first_name)
        self.assertEqual("Dlamini", trainer.last_name)
        self.assertEqual("thandi.example@example.edu", trainer.email)
        self.assertEqual("555-1001", trainer.phone)
        self.assertEqual(TRAINER_ACTIVE_STATUS, trainer.status)

    def test_blank_required_fields_are_rejected(self):
        cases = [
            {"trainer_number": "", "first_name": "Thandi", "last_name": "Dlamini"},
            {"trainer_number": "TRN-1001", "first_name": " ", "last_name": "Dlamini"},
            {"trainer_number": "TRN-1001", "first_name": "Thandi", "last_name": ""},
        ]

        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValidationError):
                    self.service.register_trainer(**kwargs)

    def test_invalid_email_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.service.register_trainer(
                "TRN-1001",
                "Thandi",
                "Dlamini",
                "not-an-email",
                None,
            )

    def test_duplicate_identifier_and_email_are_translated(self):
        self.service.register_trainer(
            "TRN-1001",
            "Thandi",
            "Dlamini",
            "thandi@example.edu",
        )

        with self.assertRaisesRegex(DuplicateRecordError, "Trainer number"):
            self.service.register_trainer("trn-1001", "Bongi", "Mokoena")
        with self.assertRaisesRegex(DuplicateRecordError, "Email address"):
            self.service.register_trainer(
                "TRN-1002",
                "Bongi",
                "Mokoena",
                "THANDI@EXAMPLE.EDU",
            )

    def test_get_missing_trainer_raises_not_found(self):
        with self.assertRaisesRegex(RecordNotFoundError, "TRN-9999"):
            self.service.get_trainer_by_number("trn-9999")

    def test_update_trainer_changes_mutable_fields(self):
        self.service.register_trainer("TRN-1001", "Thandi", "Dlamini")

        updated = self.service.update_trainer(
            trainer_number="TRN-1001",
            first_name="Thando",
            last_name="Naidoo",
            email="thando@example.edu",
            phone="555-2002",
        )

        self.assertEqual("TRN-1001", updated.trainer_number)
        self.assertEqual("Thando", updated.first_name)
        self.assertEqual("Naidoo", updated.last_name)
        self.assertEqual("thando@example.edu", updated.email)
        self.assertEqual("555-2002", updated.phone)

    def test_invalid_update_is_rejected(self):
        self.service.register_trainer("TRN-1001", "Thandi", "Dlamini")

        with self.assertRaises(ValidationError):
            self.service.update_trainer(
                trainer_number="TRN-1001",
                first_name="",
                last_name="Dlamini",
            )

    def test_repeated_deactivate_is_safe_and_keeps_inactive_status(self):
        registered = self.service.register_trainer("TRN-1001", "Thandi", "Dlamini")

        first_result = self.service.deactivate_trainer("TRN-1001")
        second_result = self.service.deactivate_trainer("TRN-1001")

        self.assertEqual(registered.trainer_id, first_result.trainer_id)
        self.assertEqual(registered.trainer_id, second_result.trainer_id)
        self.assertEqual(TRAINER_INACTIVE_STATUS, first_result.status)
        self.assertEqual(TRAINER_INACTIVE_STATUS, second_result.status)

    def test_reactivate_uses_same_record(self):
        registered = self.service.register_trainer("TRN-1001", "Thandi", "Dlamini")
        self.service.deactivate_trainer("TRN-1001")

        reactivated = self.service.reactivate_trainer("TRN-1001")

        self.assertEqual(registered.trainer_id, reactivated.trainer_id)
        self.assertEqual(TRAINER_ACTIVE_STATUS, reactivated.status)

    def test_search_and_listing_exclude_inactive_by_default(self):
        self.service.register_trainer("TRN-1001", "Thandi", "Dlamini")
        self.service.register_trainer("TRN-1002", "Ayesha", "Banda")
        self.service.deactivate_trainer("TRN-1002")

        active_trainers = self.service.list_trainers()
        all_trainers = self.service.list_trainers(include_inactive=True)

        self.assertEqual(["TRN-1001"], [trainer.trainer_number for trainer in active_trainers])
        self.assertEqual(
            ["TRN-1002", "TRN-1001"],
            [trainer.trainer_number for trainer in all_trainers],
        )
        self.assertEqual([], self.service.search_trainers("Ayesha"))
        self.assertEqual(
            ["TRN-1002"],
            [
                trainer.trainer_number
                for trainer in self.service.search_trainers(
                    " Ayesha ",
                    include_inactive=True,
                )
            ],
        )

    def test_reactivation_does_not_create_duplicate_rows(self):
        registered = self.service.register_trainer("TRN-1001", "Thandi", "Dlamini")
        self.service.deactivate_trainer("TRN-1001")
        self.service.reactivate_trainer("TRN-1001")

        with open_database(self.database_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM trainers").fetchone()[0]

        self.assertEqual(1, count)
        self.assertEqual(
            registered.trainer_id,
            self.service.get_trainer_by_number("TRN-1001").trainer_id,
        )


if __name__ == "__main__":
    unittest.main()
