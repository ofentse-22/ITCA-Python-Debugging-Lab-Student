"""Assessment domain model."""

from dataclasses import dataclass
from decimal import Decimal


ASSESSMENT_ACTIVE_STATUS = "active"
ASSESSMENT_ARCHIVED_STATUS = "archived"
ASSESSMENT_STATUSES = (
    ASSESSMENT_ACTIVE_STATUS,
    ASSESSMENT_ARCHIVED_STATUS,
)

ASSESSMENT_PRACTICAL_TYPE = "practical"
ASSESSMENT_QUIZ_TYPE = "quiz"
ASSESSMENT_TEST_TYPE = "test"
ASSESSMENT_PROJECT_TYPE = "project"
ASSESSMENT_EXAM_TYPE = "exam"
ASSESSMENT_TYPES = (
    ASSESSMENT_PRACTICAL_TYPE,
    ASSESSMENT_QUIZ_TYPE,
    ASSESSMENT_TEST_TYPE,
    ASSESSMENT_PROJECT_TYPE,
    ASSESSMENT_EXAM_TYPE,
)


@dataclass(frozen=True)
class Assessment:
    """A course or module assessment definition."""

    assessment_id: int
    course_id: int
    module_id: int | None
    assessment_name: str
    assessment_type: str
    max_mark: Decimal
    weight: Decimal | None
    pass_mark: Decimal | None
    status: str
    created_at: str
    updated_at: str

    @property
    def is_active(self) -> bool:
        """Return True when the assessment can accept new marks."""
        return self.status == ASSESSMENT_ACTIVE_STATUS

    @property
    def is_archived(self) -> bool:
        """Return True when the assessment is archived."""
        return self.status == ASSESSMENT_ARCHIVED_STATUS

    @property
    def is_module_specific(self) -> bool:
        """Return True when the assessment targets a course module."""
        return self.assessment_id is not None

    @property
    def is_course_level(self) -> bool:
        """Return True when the assessment targets the whole course."""
        return self.module_id is None
