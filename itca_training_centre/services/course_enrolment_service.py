"""Business rules for course enrolments."""

from pathlib import Path
import logging

from ..models.course import COURSE_ACTIVE_STATUS
from ..models.course_enrolment import (
    ENROLMENT_ACTIVE_STATUS,
    ENROLMENT_CANCELLED_STATUS,
    ENROLMENT_STATUSES,
    CourseEnrolment,
)
from ..models.student import ACTIVE_STATUS
from ..repositories.course_enrolment_repository import CourseEnrolmentRepository
from ..repositories.course_repository import CourseRepository
from ..repositories.student_repository import StudentRepository
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from ..utils.logging_setup import get_application_logger
from ..utils.validators import (
    normalize_cancellation_reason,
    normalize_course_code,
    normalize_iso_date,
    normalize_status,
    normalize_student_number,
)


class CourseEnrolmentService:
    """Course enrolment workflow service."""

    def __init__(
        self,
        database_path: Path,
        repository: CourseEnrolmentRepository | None = None,
        student_repository: StudentRepository | None = None,
        course_repository: CourseRepository | None = None,
        logger: logging.Logger | None = None,
    ):
        self.repository = repository or CourseEnrolmentRepository(database_path)
        self.student_repository = student_repository or StudentRepository(database_path)
        self.course_repository = course_repository or CourseRepository(database_path)
        self.logger = logger or get_application_logger()

    def enrol_student(
        self,
        student_number: str,
        course_code: str,
        enrolment_date: str,
    ) -> CourseEnrolment:
        """Create a new active student-course enrolment."""
        student = self._get_student_by_number(student_number)
        course = self._get_course_by_code(course_code)
        normalized_date = normalize_iso_date(enrolment_date, "Enrolment date")

        if student.status != ACTIVE_STATUS:
            raise ValidationError("Student must be active before enrolling in a course.")
        if course.status != COURSE_ACTIVE_STATUS:
            raise ValidationError("Course must be active before enrolling students.")

        try:
            existing = self.repository.get_active_for_student_course(
                student.student_id,
                course.course_id,
            )
            if existing is not None:
                raise DuplicateRecordError(
                    "Student is already actively enrolled in this course."
                )

            enrolment = self.repository.create(
                student_id=student.student_id,
                course_id=course.course_id,
                enrolment_date=normalized_date,
                status=ENROLMENT_ACTIVE_STATUS,
            )
        except DuplicateRecordError:
            self.logger.warning("Course enrolment rejected because of duplicate data")
            raise
        except RecordNotFoundError:
            self.logger.warning("Course enrolment rejected because a parent is missing")
            raise
        except DatabaseError:
            self.logger.exception("Course enrolment failed")
            raise

        self.logger.info("Course enrolment created")
        return enrolment

    def get_enrolment_by_id(self, enrolment_id: int) -> CourseEnrolment:
        """Return one enrolment by database ID for display workflows."""
        try:
            enrolment = self.repository.get_by_id(enrolment_id)
        except DatabaseError:
            self.logger.exception("Course enrolment lookup failed")
            raise

        if enrolment is None:
            raise RecordNotFoundError(
                f"No course enrolment was found for ID {enrolment_id}."
            )

        return enrolment

    def list_enrolments(
        self,
        include_historical: bool = False,
        status: str | None = None,
    ) -> list[CourseEnrolment]:
        """Return enrolments, excluding historical records by default."""
        normalized_status = _normalize_optional_enrolment_status(status)

        try:
            return self.repository.list_enrolments(
                include_historical=include_historical,
                status=normalized_status,
            )
        except DatabaseError:
            self.logger.exception("Course enrolment listing failed")
            raise

    def list_student_enrolments(
        self,
        student_number: str,
        include_historical: bool = False,
        status: str | None = None,
    ) -> list[CourseEnrolment]:
        """Return enrolments for one student after validating the student exists."""
        student = self._get_student_by_number(student_number)
        normalized_status = _normalize_optional_enrolment_status(status)

        try:
            return self.repository.list_enrolments(
                include_historical=True,
                status=normalized_status,
            )
        except DatabaseError:
            self.logger.exception("Student enrolment listing failed")
            raise

    def list_course_enrolments(
        self,
        course_code: str,
        include_historical: bool = False,
        status: str | None = None,
    ) -> list[CourseEnrolment]:
        """Return enrolments for one course after validating the course exists."""
        course = self._get_course_by_code(course_code)
        normalized_status = _normalize_optional_enrolment_status(status)

        try:
            return self.repository.list_for_course(
                course_id=course.course_id,
                include_historical=include_historical,
                status=normalized_status,
            )
        except DatabaseError:
            self.logger.exception("Course enrolment listing failed")
            raise

    def list_filtered_enrolments(
        self,
        student_number: str | None = None,
        course_code: str | None = None,
        include_historical: bool = False,
        status: str | None = None,
    ) -> list[CourseEnrolment]:
        """Return enrolments using optional student and course filters."""
        normalized_status = _normalize_optional_enrolment_status(status)
        student = None
        course = None

        if student_number is not None:
            student = self._get_student_by_number(student_number)
        if course_code is not None:
            course = self._get_course_by_code(course_code)

        try:
            if student is not None and course is not None:
                return self.repository.list_for_student_course(
                    student_id=student.student_id,
                    course_id=course.course_id,
                    include_historical=include_historical,
                    status=normalized_status,
                )
            if student is not None:
                return self.repository.list_for_student(
                    student_id=student.student_id,
                    include_historical=include_historical,
                    status=normalized_status,
                )
            if course is not None:
                return self.repository.list_for_course(
                    course_id=course.course_id,
                    include_historical=include_historical,
                    status=normalized_status,
                )

            return self.repository.list_enrolments(
                include_historical=include_historical,
                status=normalized_status,
            )
        except DatabaseError:
            self.logger.exception("Course enrolment listing failed")
            raise

    def cancel_enrolment(
        self,
        student_number: str,
        course_code: str,
        cancelled_at: str,
        cancellation_reason: str,
    ) -> CourseEnrolment:
        """Cancel the active enrolment for one student/course pair."""
        student = self._get_student_by_number(student_number)
        course = self._get_course_by_code(course_code)
        normalized_cancelled_at = normalize_iso_date(cancelled_at, "Cancellation date")
        normalized_reason = normalize_cancellation_reason(cancellation_reason)

        try:
            active_enrolment = self.repository.get_active_for_student_course(
                student.student_id,
                course.course_id,
            )
            if active_enrolment is None:
                raise RecordNotFoundError(
                    "No active enrolment was found for student "
                    f"{student.student_number} in course {course.course_code}."
                )
            if normalized_cancelled_at < active_enrolment.enrolment_date:
                raise ValidationError(
                    "Cancellation date may not be before enrolment date."
                )

            cancelled = self.repository.cancel(
                enrolment_id=active_enrolment.enrolment_id,
                cancelled_at=normalized_cancelled_at,
                cancellation_reason=normalized_reason,
            )
        except DatabaseError:
            self.logger.exception("Course enrolment cancellation failed")
            raise

        if cancelled is None:
            raise RecordNotFoundError(
                "No active enrolment was found for student "
                f"{student.student_number} in course {course.course_code}."
            )

        self.logger.info("Course enrolment cancelled")
        return cancelled

    def _get_student_by_number(self, student_number: str):
        normalized_number = normalize_student_number(student_number)
        try:
            student = self.student_repository.get_by_student_number(normalized_number)
        except DatabaseError:
            self.logger.exception("Parent student lookup failed")
            raise

        if student is None:
            raise RecordNotFoundError(
                f"No student was found for number {normalized_number}."
            )

        return student

    def _get_course_by_code(self, course_code: str):
        normalized_code = normalize_course_code(course_code)
        try:
            course = self.course_repository.get_by_code(normalized_code)
        except DatabaseError:
            self.logger.exception("Parent course lookup failed")
            raise

        if course is None:
            raise RecordNotFoundError(f"No course was found for code {normalized_code}.")

        return course


def _normalize_optional_enrolment_status(status: str | None) -> str | None:
    if status is None:
        return None

    return normalize_status(status, "Enrolment status", ENROLMENT_STATUSES)
