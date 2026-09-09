"""Mark domain model and assessment-result structures."""

from dataclasses import dataclass
from decimal import Decimal

from .assessment import Assessment


RESULT_PASS_STATE = "pass"
RESULT_FAIL_STATE = "fail"


@dataclass(frozen=True)
class Mark:
    """One authoritative student mark for one assessment."""

    mark_id: int
    assessment_id: int
    student_id: int
    mark_obtained: Decimal
    captured_at: str
    notes: str | None


@dataclass(frozen=True)
class MarkCaptureEntry:
    """Validated input for one class mark-capture row."""

    student_number: str
    mark_obtained: Decimal | int | str
    notes: str | None = None


@dataclass(frozen=True)
class AssessmentResult:
    """A mark with its assessment context and derived result state."""

    mark: Mark
    assessment: Assessment
    percentage: Decimal
    result_state: str | None

    @property
    def has_result_state(self) -> bool:
        """Return True when pass/fail is defined for the assessment."""
        return self.result_state is not None


@dataclass(frozen=True)
class AssessmentSummary:
    """Assessment-domain aggregate values."""

    assessment_id: int
    recorded_count: int
    average_mark: Decimal | None
    average_percentage: Decimal | None
    highest_mark: Decimal | None
    lowest_mark: Decimal | None
    pass_count: int | None
    fail_count: int | None
    pass_rate: Decimal | None

    @property
    def has_results(self) -> bool:
        """Return True when at least one mark has been recorded."""
        return self.recorded_count > 0

    @property
    def has_pass_fail_counts(self) -> bool:
        """Return True when pass/fail counts were calculated."""
        return self.pass_count is not None and self.fail_count is not None
