"""Course enrolment domain model."""

from dataclasses import dataclass


ENROLMENT_ACTIVE_STATUS = "active"
ENROLMENT_COMPLETED_STATUS = "completed"
ENROLMENT_CANCELLED_STATUS = "cancelled"
ENROLMENT_STATUSES = (
    ENROLMENT_ACTIVE_STATUS,
    ENROLMENT_COMPLETED_STATUS,
    ENROLMENT_CANCELLED_STATUS,
)


@dataclass(frozen=True)
class CourseEnrolment:
    """A student's enrolment relationship with a course."""

    enrolment_id: int
    student_id: int
    course_id: int
    enrolment_date: str
    status: str
    cancelled_at: str | None
    cancellation_reason: str | None
    created_at: str
    updated_at: str

    @property
    def is_active(self) -> bool:
        """Return True when the enrolment is active."""
        return self.status == ENROLMENT_ACTIVE_STATUS

    @property
    def is_cancelled(self) -> bool:
        """Return True when the enrolment was cancelled."""
        return self.status == ENROLMENT_CANCELLED_STATUS

    @property
    def is_historical(self) -> bool:
        """Return True when this enrolment is no longer active."""
        return self.status in (ENROLMENT_CANCELLED_STATUS, ENROLMENT_COMPLETED_STATUS)
