"""Attendance session domain model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AttendanceSession:
    """A course attendance session from the training-centre database."""

    session_id: int
    course_id: int
    session_date: str
    topic: str
    created_at: str

    @property
    def has_topic(self) -> bool:
        """Return True when the session has a non-blank topic."""
        return bool(self.topic.strip())
