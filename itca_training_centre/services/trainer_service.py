"""Business rules for trainer management."""

from pathlib import Path
import logging

from ..models.trainer import TRAINER_ACTIVE_STATUS, TRAINER_INACTIVE_STATUS, Trainer
from ..repositories.trainer_repository import TrainerRepository
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    RecordNotFoundError,
)
from ..utils.logging_setup import get_application_logger
from ..utils.validators import (
    normalize_required_text,
    normalize_trainer_email,
    normalize_trainer_name,
    normalize_trainer_number,
    normalize_trainer_phone,
)


class TrainerService:
    """Trainer business workflow service."""

    def __init__(
        self,
        database_path: Path,
        repository: TrainerRepository | None = None,
        logger: logging.Logger | None = None,
    ):
        self.repository = repository or TrainerRepository(database_path)
        self.logger = logger or get_application_logger()

    def register_trainer(
        self,
        trainer_number: str,
        first_name: str,
        last_name: str,
        email: str | None = None,
        phone: str | None = None,
    ) -> Trainer:
        """Validate, create, and return a new trainer."""
        values = self._normalize_trainer_fields(
            trainer_number=trainer_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
        )
        existing_trainer = self.repository.get_by_number(values["trainer_number"])
        if existing_trainer is None:
            raise DuplicateRecordError("Trainer number already exists.")

        try:
            trainer = self.repository.create(**values)
        except DuplicateRecordError:
            self.logger.warning("Trainer registration rejected because of duplicate data")
            raise
        except DatabaseError:
            self.logger.exception("Trainer registration failed")
            raise

        self.logger.info("Trainer registered")
        return trainer

    def get_trainer_by_id(self, trainer_id: int) -> Trainer:
        """Return one trainer by database ID for relationship display."""
        try:
            trainer = self.repository.get_by_id(trainer_id)
        except DatabaseError:
            self.logger.exception("Trainer lookup failed")
            raise

        if trainer is None:
            raise RecordNotFoundError(f"No trainer was found for ID {trainer_id}.")

        return trainer

    def get_trainer_by_number(self, trainer_number: str) -> Trainer:
        """Return one trainer, raising RecordNotFoundError when missing."""
        normalized_number = normalize_trainer_number(trainer_number)

        try:
            trainer = self.repository.get_by_number(normalized_number)
        except DatabaseError:
            self.logger.exception("Trainer lookup failed")
            raise

        if trainer is None:
            raise RecordNotFoundError(
                f"No trainer was found for number {normalized_number}."
            )

        return trainer

    def list_trainers(self, include_inactive: bool = False) -> list[Trainer]:
        """Return trainers, excluding inactive records by default."""
        try:
            return self.repository.list_trainers(include_inactive=include_inactive)
        except DatabaseError:
            self.logger.exception("Trainer listing failed")
            raise

    def search_trainers(
        self,
        search_text: str,
        include_inactive: bool = False,
    ) -> list[Trainer]:
        """Search trainers by approved trainer fields."""
        normalized_search = normalize_required_text(search_text, "Search text")

        try:
            return self.repository.search(
                normalized_search,
                include_inactive=include_inactive,
            )
        except DatabaseError:
            self.logger.exception("Trainer search failed")
            raise

    def update_trainer(
        self,
        trainer_number: str,
        first_name: str,
        last_name: str,
        email: str | None = None,
        phone: str | None = None,
    ) -> Trainer:
        """Update mutable trainer fields for an existing trainer."""
        existing_trainer = self.get_trainer_by_number(trainer_number)
        values = self._normalize_trainer_fields(
            trainer_number=existing_trainer.trainer_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
        )

        try:
            updated_trainer = self.repository.update(
                trainer_id=existing_trainer.trainer_id,
                first_name=values["first_name"],
                last_name=values["last_name"],
                email=values["email"],
                phone=values["phone"],
            )
        except DuplicateRecordError:
            self.logger.warning("Trainer update rejected because of duplicate data")
            raise
        except DatabaseError:
            self.logger.exception("Trainer update failed")
            raise

        if updated_trainer is None:
            raise RecordNotFoundError(
                f"No trainer was found for number {existing_trainer.trainer_number}."
            )

        self.logger.info("Trainer updated")
        return updated_trainer

    def deactivate_trainer(self, trainer_number: str) -> Trainer:
        """Set a trainer to inactive without deleting the row."""
        trainer = self.get_trainer_by_number(trainer_number)
        if trainer.status == TRAINER_INACTIVE_STATUS:
            self.logger.info("Trainer deactivation requested for already inactive record")
            return trainer

        try:
            updated_trainer = self.repository.deactivate(trainer.trainer_id)
        except DatabaseError:
            self.logger.exception("Trainer deactivation failed")
            raise

        if updated_trainer is None:
            raise RecordNotFoundError(
                f"No trainer was found for number {trainer.trainer_number}."
            )

        self.logger.info("Trainer deactivated")
        return updated_trainer

    def reactivate_trainer(self, trainer_number: str) -> Trainer:
        """Set a trainer back to active using the existing row."""
        trainer = self.get_trainer_by_number(trainer_number)
        if trainer.status == TRAINER_ACTIVE_STATUS:
            self.logger.info("Trainer reactivation requested for already active record")
            return trainer

        try:
            updated_trainer = self.repository.reactivate(trainer.trainer_id)
        except DatabaseError:
            self.logger.exception("Trainer reactivation failed")
            raise

        if updated_trainer is None:
            raise RecordNotFoundError(
                f"No trainer was found for number {trainer.trainer_number}."
            )

        self.logger.info("Trainer reactivated")
        return updated_trainer

    def _normalize_trainer_fields(
        self,
        trainer_number: str,
        first_name: str,
        last_name: str,
        email: str | None,
        phone: str | None,
    ) -> dict[str, str | None]:
        return {
            "trainer_number": normalize_trainer_number(trainer_number),
            "first_name": normalize_trainer_name(first_name, "First name"),
            "last_name": normalize_trainer_name(last_name, "Last name"),
            "email": normalize_trainer_email(email),
            "phone": normalize_trainer_phone(phone),
        }
