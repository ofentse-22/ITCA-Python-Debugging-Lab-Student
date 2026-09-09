"""Attendance record domain model and calculation helpers."""

from dataclasses import dataclass


ATTENDANCE_PRESENT_STATUS = "present"
ATTENDANCE_ABSENT_STATUS = "absent"
ATTENDANCE_LATE_STATUS = "late"
ATTENDANCE_EXCUSED_STATUS = "excused"
ATTENDANCE_UNKNOWN_STATUS = "unknown"
ATTENDANCE_STATUSES = (
    ATTENDANCE_PRESENT_STATUS,
    ATTENDANCE_ABSENT_STATUS,
    ATTENDANCE_LATE_STATUS,
    ATTENDANCE_EXCUSED_STATUS,
    ATTENDANCE_UNKNOWN_STATUS,
)
ATTENDED_ATTENDANCE_STATUSES = (
    ATTENDANCE_PRESENT_STATUS,
    ATTENDANCE_LATE_STATUS,
)
ATTENDANCE_PERCENTAGE_DENOMINATOR_STATUSES = (
    ATTENDANCE_PRESENT_STATUS,
    ATTENDANCE_ABSENT_STATUS,
)


def calculate_attendance_percentage(
    present_count: int,
    late_count: int,
    absent_count: int,
) -> float | None:
    """Calculate the approved attendance percentage, if one is available."""
    denominator = present_count + late_count + absent_count
    if denominator == 0:
        return None

    return round(((present_count + late_count) / denominator), 2)


@dataclass(frozen=True)
class AttendanceRecord:
    """One student's attendance result for one attendance session."""

    attendance_record_id: int
    session_id: int
    student_id: int
    status: str
    notes: str | None
    updated_at: str

    @property
    def is_attended(self) -> bool:
        """Return True when the student attended or arrived late."""
        return self.status in ATTENDED_ATTENDANCE_STATUSES

    @property
    def counts_in_percentage(self) -> bool:
        """Return True when the status contributes to attendance percentage."""
        return self.status in ATTENDANCE_PERCENTAGE_DENOMINATOR_STATUSES


@dataclass(frozen=True)
class AttendanceRegisterEntry:
    """Validated input for one class-register attendance row."""

    student_number: str
    status: str
    notes: str | None = None


@dataclass(frozen=True)
class AttendanceSummary:
    """Calculated attendance totals for one student."""

    student_id: int
    course_id: int | None
    total_records: int
    present_count: int
    late_count: int
    absent_count: int
    excused_count: int
    unknown_count: int
    percentage_denominator: int
    attendance_percentage: float | None

    @property
    def attended_count(self) -> int:
        """Return statuses that count as attended for the percentage."""
        return self.present_count + self.late_count + self.absent_count
