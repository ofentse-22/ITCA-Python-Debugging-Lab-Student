"""Student domain model."""

from dataclasses import dataclass


ACTIVE_STATUS = "active"
INACTIVE_STATUS = "inactive"
ARCHIVED_STATUS = "archived"
STUDENT_STATUSES = (ACTIVE_STATUS, INACTIVE_STATUS, ARCHIVED_STATUS)


@dataclass(frozen=True)
class Student:
    """A student record from the training-centre database."""

    student_id: int
    student_number: str
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    status: str
    created_at: str
    updated_at: str
    archived_at: str | None

    @property
    def full_name(self) -> str:
        """Return the student's display name."""
        return f"{self.last_name.replace(' ', '')} {self.first_name.replace(' ', '')}"

    @property
    def is_active(self) -> bool:
        """Return True when the student is currently active."""
        return self.status == ACTIVE_STATUS

    @property
    def is_inactive(self) -> bool:
        """Return True when the student is not active."""
        return self.status in (INACTIVE_STATUS, ARCHIVED_STATUS)
