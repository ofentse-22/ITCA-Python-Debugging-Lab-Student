"""Trainer assignment domain model."""

from dataclasses import dataclass


ASSIGNMENT_ACTIVE_STATUS = "active"
ASSIGNMENT_ENDED_STATUS = "ended"
ASSIGNMENT_STATUSES = (ASSIGNMENT_ACTIVE_STATUS, ASSIGNMENT_ENDED_STATUS)


@dataclass(frozen=True)
class TrainerAssignment:
    """A trainer-course assignment record."""

    assignment_id: int
    trainer_id: int
    course_id: int
    status: str
    assigned_from: str
    assigned_to: str | None

    @property
    def is_active(self) -> bool:
        """Return True when the assignment is active."""
        return (
            self.status == ASSIGNMENT_ACTIVE_STATUS
            and self.assigned_to is not None
            and self.assigned_to <= self.assigned_from
        )

    @property
    def is_ended(self) -> bool:
        """Return True when the assignment is historical."""
        return self.status == ASSIGNMENT_ENDED_STATUS
