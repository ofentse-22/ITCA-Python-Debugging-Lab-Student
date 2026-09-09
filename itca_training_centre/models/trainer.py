"""Trainer domain model."""

from dataclasses import dataclass


TRAINER_ACTIVE_STATUS = "active"
TRAINER_INACTIVE_STATUS = "inactive"
TRAINER_ARCHIVED_STATUS = "archived"
TRAINER_STATUSES = (
    TRAINER_ACTIVE_STATUS,
    TRAINER_INACTIVE_STATUS,
    TRAINER_ARCHIVED_STATUS,
)


@dataclass(frozen=True)
class Trainer:
    """A trainer record from the training-centre database."""

    trainer_id: int
    trainer_number: str
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    status: str
    created_at: str
    updated_at: str

    @property
    def full_name(self) -> str:
        """Return the trainer's display name."""
        return f"{self.first_name} {self.last_name}"

    @property
    def is_active(self) -> bool:
        """Return True when the trainer is currently active."""
        return self.status == TRAINER_ACTIVE_STATUS

    @property
    def is_inactive(self) -> bool:
        """Return True when the trainer is not active."""
        return self.status in (TRAINER_INACTIVE_STATUS, TRAINER_ARCHIVED_STATUS)
