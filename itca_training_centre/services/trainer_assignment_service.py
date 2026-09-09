"""Business rules for trainer assignments."""

from pathlib import Path
import logging

from ..cli.trainer_cli import TrainerAssignmentMenuOption
from ..models.course import COURSE_ACTIVE_STATUS
from ..models.trainer import TRAINER_ACTIVE_STATUS
from ..models.trainer_assignment import (
    ASSIGNMENT_ACTIVE_STATUS,
    ASSIGNMENT_ENDED_STATUS,
    ASSIGNMENT_STATUSES,
    TrainerAssignment,
)
from ..repositories.course_repository import CourseRepository
from ..repositories.trainer_assignment_repository import TrainerAssignmentRepository
from ..repositories.trainer_repository import TrainerRepository
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from ..utils.logging_setup import get_application_logger
from ..utils.validators import (
    normalize_course_code,
    normalize_iso_date,
    normalize_optional_iso_date,
    normalize_status,
    normalize_trainer_number,
)


class TrainerAssignmentService:
    """Trainer assignment workflow service."""

    def __init__(
        self,
        database_path: Path,
        repository: TrainerAssignmentRepository | None = None,
        trainer_repository: TrainerRepository | None = None,
        course_repository: CourseRepository | None = None,
        logger: logging.Logger | None = None,
    ):
        self.repository = repository or TrainerAssignmentRepository(database_path)
        self.trainer_repository = trainer_repository or TrainerRepository(database_path)
        self.course_repository = course_repository or CourseRepository(database_path)
        self.logger = logger or get_application_logger()

    def assign_trainer(
        self,
        trainer_number: str,
        course_code: str,
        assigned_from: str,
    ) -> TrainerAssignment:
        """Create a new active trainer-course assignment."""
        trainer = self._get_trainer_by_number(trainer_number)
        course = self._get_course_by_code(course_code)
        normalized_assigned_from = normalize_iso_date(assigned_from, "Assigned from")

        self._validate_active_parents(trainer, course)

        try:
            existing = self.repository.get_active_for_trainer_course(
                trainer.trainer_id,
                course.course_id,
            )
            if existing is not None:
                raise DuplicateRecordError(
                    "Trainer is already actively assigned to this course."
                )

            assignment = self.repository.create(
                trainer_id=trainer.trainer_id,
                course_id=course.course_id,
                assigned_from=normalized_assigned_from,
                status=ASSIGNMENT_ACTIVE_STATUS,
            )
        except DuplicateRecordError:
            self.logger.warning("Trainer assignment rejected because of duplicate data")
            raise
        except RecordNotFoundError:
            self.logger.warning("Trainer assignment rejected because a parent is missing")
            raise
        except DatabaseError:
            self.logger.exception("Trainer assignment failed")
            raise

        self.logger.info("Trainer assignment created")
        return assignment

    def get_assignment_by_id(self, assignment_id: int) -> TrainerAssignment:
        """Return one assignment by database ID for display workflows."""
        try:
            assignment = self.repository.get_by_id(assignment_id)
        except DatabaseError:
            self.logger.exception("Trainer assignment lookup failed")
            raise

        if assignment is None:
            raise RecordNotFoundError(
                f"No trainer assignment was found for ID {assignment_id}."
            )

        return assignment

    def list_assignments(
        self,
        include_ended: bool = False,
        status: str | None = None,
    ) -> list[TrainerAssignment]:
        """Return assignments, excluding ended records by default."""
        normalized_status = _normalize_optional_assignment_status(status)

        try:
            return self.repository.list_assignments(
                include_ended=include_ended,
                status=normalized_status,
            )
        except DatabaseError:
            self.logger.exception("Trainer assignment listing failed")
            raise

    def list_trainer_assignments(
        self,
        trainer_number: str,
        include_ended: bool = False,
        status: str | None = None,
    ) -> list[TrainerAssignment]:
        """Return assignments for one trainer."""
        trainer = self._get_trainer_by_number(trainer_number)
        normalized_status = _normalize_optional_assignment_status(status)

        try:
            return self.repository.list_for_trainer(
                trainer_id=trainer.trainer_id,
                include_ended=include_ended,
                status=normalized_status,
            )
        except DatabaseError:
            self.logger.exception("Trainer assignment listing failed")
            raise

    def list_course_assignments(
        self,
        course_code: str,
        include_ended: bool = False,
        status: str | None = None,
    ) -> list[TrainerAssignment]:
        """Return assignments for one course."""
        course = self._get_course_by_code(course_code)
        normalized_status = _normalize_optional_assignment_status(status)

        try:
            return self.repository.list_for_course(
                course_id=course.course_id,
                include_ended=include_ended,
                status=normalized_status,
            )
        except DatabaseError:
            self.logger.exception("Trainer assignment listing failed")
            raise

    def list_filtered_assignments(
        self,
        trainer_number: str | None = None,
        course_code: str | None = None,
        include_ended: bool = False,
        status: str | None = None,
    ) -> list[TrainerAssignment]:
        """Return assignments using optional trainer and course filters."""
        normalized_status = _normalize_optional_assignment_status(status)
        trainer = None
        course = None

        if trainer_number is not None:
            trainer = self._get_trainer_by_number(trainer_number)
        if course_code is not None:
            course = self._get_course_by_code(course_code)

        try:
            if trainer is not None and course is not None:
                return self.repository.list_for_trainer_course(
                    trainer_id=trainer.trainer_id,
                    course_id=course.course_id,
                    include_ended=include_ended,
                    status=normalized_status,
                )
            if trainer is not None:
                return self.repository.list_for_trainer(
                    trainer_id=trainer.trainer_id,
                    include_ended=include_ended,
                    status=normalized_status,
                )
            if course is not None:
                return self.repository.list_for_course(
                    course_id=course.course_id,
                    include_ended=include_ended,
                    status=normalized_status,
                )

            return self.repository.list_assignments(
                include_ended=include_ended,
                status=normalized_status,
            )
        except DatabaseError:
            self.logger.exception("Trainer assignment listing failed")
            raise

    def end_assignment(
        self,
        trainer_number: str,
        course_code: str,
        assigned_to: str | None = None,
    ) -> TrainerAssignment:
        """End the active assignment for one trainer/course pair."""
        trainer = self._get_trainer_by_number(trainer_number)
        course = self._get_course_by_code(course_code)
        normalized_assigned_to = normalize_optional_iso_date(assigned_to, "Assigned to")

        try:
            active_assignment = self.repository.get_active_for_trainer_course(
                trainer.trainer_id,
                course.course_id,
            )
            if active_assignment is None:
                raise RecordNotFoundError(
                    "No active assignment was found for trainer "
                    f"{trainer.trainer_number} in course {course.course_code}."
                )
            if (
                normalized_assigned_to is not None
                and normalized_assigned_to < active_assignment.assigned_from
            ):
                raise ValidationError(
                    "Assigned to date may not be before assigned from date."
                )

            ended = self.repository.end(
                assignment_id=active_assignment.assignment_id,
                assigned_to=normalized_assigned_to,
            )
        except DatabaseError:
            self.logger.exception("Trainer assignment deactivation failed")
            raise

        if ended is None:
            raise RecordNotFoundError(
                "No active assignment was found for trainer "
                f"{trainer.trainer_number} in course {course.course_code}."
            )

        self.logger.info("Trainer assignment ended")
        return ended

    def reactivate_assignment(
        self,
        trainer_number: str,
        course_code: str,
    ) -> TrainerAssignment:
        """Reactivate the latest ended assignment if no active one exists."""
        trainer = self._get_trainer_by_number(trainer_number)
        course = self._get_course_by_code(course_code)
        self._validate_active_parents(trainer, course)

        try:
            active_assignment = self.repository.get_active_for_trainer_course(
                trainer.trainer_id,
                course.course_id,
            )
            if active_assignment is not None:
                self.logger.info(
                    "Trainer assignment reactivation requested for already active record"
                )
                return active_assignment

            latest_assignment = self.repository.get_latest_for_trainer_course(
                trainer.trainer_id,
                course.course_id,
            )
            if latest_assignment is None:
                raise RecordNotFoundError(
                    "No trainer assignment was found for trainer "
                    f"{trainer.trainer_number} in course {course.course_code}."
                )
            if latest_assignment.status != ASSIGNMENT_ENDED_STATUS:
                raise RecordNotFoundError(
                    "No ended assignment was found for trainer "
                    f"{trainer.trainer_number} in course {course.course_code}."
                )

            reactivated = self.repository.reactivate(latest_assignment.assignment_id)
        except DuplicateRecordError:
            self.logger.warning("Trainer assignment reactivation rejected as duplicate")
            raise
        except DatabaseError:
            self.logger.exception("Trainer assignment reactivation failed")
            raise

        if reactivated is None:
            raise RecordNotFoundError(
                "No trainer assignment was found for trainer "
                f"{trainer.trainer_number} in course {course.course_code}."
            )

        self.logger.info("Trainer assignment reactivated")
        return reactivated

    def _get_trainer_by_number(self, trainer_number: str):
        normalized_number = normalize_trainer_number(trainer_number)
        try:
            trainer = self.trainer_repository.get_by_number(normalized_number)
        except DatabaseError:
            self.logger.exception("Parent trainer lookup failed")
            raise

        if trainer is None:
            raise RecordNotFoundError(
                f"No trainer was found for number {normalized_number}."
            )

        return trainer

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

    def _validate_active_parents(self, trainer, course) -> None:
        if trainer.status != TRAINER_ACTIVE_STATUS:
            raise ValidationError("Trainer must be active before assignment.")
        if course.status != COURSE_ACTIVE_STATUS:
            raise ValidationError("Course must be active before assigning trainers.")


def _normalize_optional_assignment_status(status: str | None) -> str | None:
    if status is None:
        return None

    return normalize_status(status, "Assignment status", ASSIGNMENT_STATUSES)
