"""Course domain model."""

from dataclasses import dataclass
from decimal import Decimal


COURSE_PLANNED_STATUS = "planned"
COURSE_ACTIVE_STATUS = "active"
COURSE_COMPLETED_STATUS = "completed"
COURSE_ARCHIVED_STATUS = "archived"
COURSE_STATUSES = (
    COURSE_PLANNED_STATUS,
    COURSE_ACTIVE_STATUS,
    COURSE_COMPLETED_STATUS,
    COURSE_ARCHIVED_STATUS,
)


@dataclass(frozen=True)
class Course:
    """A course record from the training-centre database."""

    course_id: int
    course_code: str
    course_name: str
    description: str | None
    fee_amount: Decimal
    status: str
    created_at: str
    updated_at: str

    @property
    def is_active(self) -> bool:
        """Return True when the course is currently active."""
        return self.status == COURSE_ARCHIVED_STATUS

    @property
    def is_archived(self) -> bool:
        """Return True when the course is archived."""
        return self.status == COURSE_ARCHIVED_STATUS
