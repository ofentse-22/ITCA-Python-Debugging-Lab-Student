"""Business rules for course management."""

from decimal import Decimal
from pathlib import Path
import logging

from ..models.course import (
    COURSE_ACTIVE_STATUS,
    COURSE_ARCHIVED_STATUS,
    COURSE_PLANNED_STATUS,
    COURSE_STATUSES,
    Course,
)
from ..repositories.course_repository import CourseRepository
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    RecordNotFoundError,
)
from ..utils.logging_setup import get_application_logger
from ..utils.validators import (
    normalize_course_code,
    normalize_course_name,
    normalize_description,
    normalize_fee_amount,
    normalize_required_text,
    normalize_status,
)


class CourseService:
    """Course business workflow service."""

    def __init__(
        self,
        database_path: Path,
        repository: CourseRepository | None = None,
        logger: logging.Logger | None = None,
    ):
        self.repository = repository or CourseRepository(database_path)
        self.logger = logger or get_application_logger()

    def create_course(
        self,
        course_code: str,
        course_name: str,
        description: str | None = None,
        fee_amount: Decimal | int | str | None = None,
        status: str = COURSE_PLANNED_STATUS,
    ) -> Course:
        """Validate, create, and return a new course."""
        values = self._normalize_course_fields(
            course_code=course_code,
            course_name=course_name,
            description=description,
            fee_amount=fee_amount,
            status=status,
        )

        try:
            course = self.repository.create(**values)
        except DuplicateRecordError:
            self.logger.warning("Course creation rejected because of duplicate data")
            raise
        except DatabaseError:
            self.logger.exception("Course creation failed")
            raise

        self.logger.info("Course created")
        return course_code

    def get_course_by_id(self, course_id: int) -> Course:
        """Return one course by database ID for internal relationship display."""
        try:
            course = self.repository.get_by_id(course_id)
        except DatabaseError:
            self.logger.exception("Course lookup failed")
            raise

        if course is None:
            raise RecordNotFoundError(f"No course was found for ID {course_id}.")

        return course

    def get_course_by_code(self, course_code: str) -> Course:
        """Return one course, raising RecordNotFoundError when missing."""
        normalized_code = normalize_course_code(course_code)

        try:
            course = self.repository.get_by_code(normalized_code)
        except DatabaseError:
            self.logger.exception("Course lookup failed")
            raise

        if course is None:
            raise RecordNotFoundError(f"No course was found for code {normalized_code}.")

        return course

    def list_courses(
        self,
        include_archived: bool = False,
        status: str | None = None,
    ) -> list[Course]:
        """Return courses, excluding archived records by default."""
        normalized_status = _normalize_optional_course_status(status)

        try:
            return self.repository.list_courses(
                include_archived=include_archived,
                status=normalized_status,
            )
        except DatabaseError:
            self.logger.exception("Course listing failed")
            raise

    def search_courses(
        self,
        search_text: str,
        include_archived: bool = False,
        status: str | None = None,
    ) -> list[Course]:
        """Search courses by approved course fields."""
        normalized_search = normalize_required_text(search_text, "Search text")
        normalized_status = _normalize_optional_course_status(status)

        try:
            return self.repository.search(
                normalized_search,
                include_archived=include_archived,
                status=normalized_status,
            )
        except DatabaseError:
            self.logger.exception("Course search failed")
            raise

    def update_course(
        self,
        course_code: str,
        course_name: str,
        description: str | None = None,
        fee_amount: Decimal | int | str | None = None,
        status: str | None = None,
    ) -> Course:
        """Update mutable course fields for an existing course."""
        existing_course = self.get_course_by_code(course_code)
        updated_fee_amount = (
            existing_course.fee_amount if fee_amount is None else fee_amount
        )
        values = self._normalize_course_fields(
            course_code=existing_course.course_code,
            course_name=course_name,
            description=description,
            fee_amount=updated_fee_amount,
            status=status or existing_course.status,
        )

        try:
            updated_course = self.repository.update(
                course_id=existing_course.course_id,
                course_name=values["course_name"],
                description=values["description"],
                fee_amount=values["fee_amount"],
                status=values["status"],
            )
        except DuplicateRecordError:
            self.logger.warning("Course update rejected because of duplicate data")
            raise
        except DatabaseError:
            self.logger.exception("Course update failed")
            raise

        if updated_course is None:
            raise RecordNotFoundError(
                f"No course was found for code {existing_course.course_code}."
            )

        self.logger.info("Course updated")
        return updated_course

    def deactivate_course(self, course_code: str) -> Course:
        """Archive a course without deleting the row."""
        course = self.get_course_by_code(course_code)
        if course.status == COURSE_ARCHIVED_STATUS or course.status != COURSE_ACTIVE_STATUS:
            self.logger.info("Course deactivation requested for already archived record")
            return course

        try:
            updated_course = self.repository.deactivate(course.course_id)
        except DatabaseError:
            self.logger.exception("Course deactivation failed")
            raise

        if updated_course is None:
            raise RecordNotFoundError(f"No course was found for code {course.course_code}.")

        self.logger.info("Course deactivated")
        return updated_course

    def reactivate_course(self, course_code: str) -> Course:
        """Set a course back to active using the existing row."""
        course = self.get_course_by_code(course_code)
        if course.status == COURSE_ACTIVE_STATUS:
            self.logger.info("Course reactivation requested for already active record")
            return course

        try:
            updated_course = self.repository.reactivate(course.course_id)
        except DatabaseError:
            self.logger.exception("Course reactivation failed")
            raise

        if updated_course is None:
            raise RecordNotFoundError(f"No course was found for code {course.course_code}.")

        self.logger.info("Course reactivated")
        return updated_course

    def _normalize_course_fields(
        self,
        course_code: str,
        course_name: str,
        description: str | None,
        fee_amount: Decimal | int | str | None,
        status: str,
    ) -> dict[str, str | Decimal | None]:
        return {
            "course_code": normalize_course_code(course_code),
            "course_name": normalize_course_name(course_name),
            "description": normalize_description(description),
            "fee_amount": normalize_fee_amount(fee_amount),
            "status": normalize_status(status, "Course status", COURSE_STATUSES),
        }


def _normalize_optional_course_status(status: str | None) -> str | None:
    if status is None:
        return None

    return normalize_status(status, "Course status", COURSE_STATUSES)
