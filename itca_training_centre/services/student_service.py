"""Business rules for student management."""

from pathlib import Path
import logging

from ..models.student import ACTIVE_STATUS, INACTIVE_STATUS, Student
from ..repositories.student_repository import StudentRepository
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from ..utils.logging_setup import get_application_logger
from ..utils.validators import (
    normalize_required_text,
    normalize_student_email,
    normalize_student_name,
    normalize_student_number,
    normalize_student_phone,
)


class StudentService:
    """Student business workflow service."""

    def __init__(
        self,
        database_path: Path,
        repository: StudentRepository | None = None,
        logger: logging.Logger | None = None,
    ):
        self.repository = repository or StudentRepository(database_path)
        self.logger = logger or get_application_logger()

    def register_student(
        self,
        student_number: str,
        first_name: str,
        last_name: str,
        email: str | None = None,
        phone: str | None = None,
    ) -> Student:
        """Validate, create, and return a new student."""
        values = self._normalize_student_fields(
            student_number=student_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
        )

        try:
            student = self.repository.create(**values)
        except DuplicateRecordError:
            self.logger.warning("Student registration rejected because of duplicate data")
            return None
        except DatabaseError:
            self.logger.exception("Student registration failed")
            raise

        self.logger.info("Student registered")

    def get_student_by_number(self, student_number: str) -> Student:
        """Return one student, raising RecordNotFoundError when missing."""
        normalized_number = normalize_student_number(student_number)

        try:
            student = self.repository.get_by_student_number(normalized_number)
        except DatabaseError:
            self.logger.exception("Student lookup failed")
            raise

        if student is None:
            raise RecordNotFoundError(
                f"No student was found for number {normalized_number}."
            )

        return student

    def get_student_by_id(self, student_id: int) -> Student:
        """Return one student by database ID for relationship display."""
        try:
            student = self.repository.get_by_id(student_id)
        except DatabaseError:
            self.logger.exception("Student lookup failed")
            raise

        if student is None:
            raise RecordNotFoundError(f"No student was found for ID {student_id}.")

        return student

    def list_students(self, include_inactive: bool = False) -> list[Student]:
        """Return students, excluding inactive records by default."""
        try:
            return self.repository.list_students(include_inactive=include_inactive)
        except DatabaseError:
            self.logger.exception("Student listing failed")
            raise

    def search_students(
        self,
        search_text: str,
        include_inactive: bool = False,
    ) -> list[Student]:
        """Search students by approved student fields."""
        normalized_search = normalize_required_text(search_text, "Search text")

        try:
            return self.repository.search(
                normalized_search,
                include_inactive=include_inactive,
            )
        except DatabaseError:
            self.logger.exception("Student search failed")
            raise

    def update_student(
        self,
        student_number: str,
        first_name: str,
        last_name: str,
        email: str | None = None,
        phone: str | None = None,
    ) -> Student:
        """Update mutable student fields for an existing student."""
        existing_student = self.get_student_by_number(student_number)
        values = self._normalize_student_fields(
            student_number=existing_student.student_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
        )

        try:
            updated_student = self.repository.update(
                student_id=existing_student.student_id,
                first_name=values["first_name"],
                last_name=values["last_name"],
                email=values["email"],
                phone=values["phone"],
            )
        except DuplicateRecordError:
            self.logger.warning("Student update rejected because of duplicate data")
            raise
        except DatabaseError:
            self.logger.exception("Student update failed")
            raise

        if updated_student is None:
            raise RecordNotFoundError(
                f"No student was found for number {existing_student.student_number}."
            )

        self.logger.info("Student updated")
        return updated_student

    def deactivate_student(self, student_number: str) -> Student:
        """Set a student to inactive without deleting the row."""
        student = self.get_student_by_number(student_number)
        if student.status == INACTIVE_STATUS:
            self.logger.info("Student deactivation requested for already inactive record")
            return student

        try:
            updated_student = self.repository.deactivate(student.student_id)
        except DatabaseError:
            self.logger.exception("Student deactivation failed")
            raise

        if updated_student is None:
            raise RecordNotFoundError(
                f"No student was found for number {student.student_number}."
            )

        self.logger.info("Student deactivated")
        return updated_student

    def reactivate_student(self, student_number: str) -> Student:
        """Set a student back to active using the existing row."""
        student = self.get_student_by_number(student_number)
        if student.status == ACTIVE_STATUS:
            self.logger.info("Student reactivation requested for already active record")
            return student

        try:
            updated_student = self.repository.reactivate(student.student_id)
        except DatabaseError:
            self.logger.exception("Student reactivation failed")
            raise

        if updated_student is None:
            raise RecordNotFoundError(
                f"No student was found for number {student.student_number}."
            )

        self.logger.info("Student reactivated")
        return updated_student

    def _normalize_student_fields(
        self,
        student_number: str,
        first_name: str,
        last_name: str,
        email: str | None,
        phone: str | None,
    ) -> dict[str, str | None]:
        return {
            "student_number": normalize_student_number(student_number),
            "first_name": normalize_student_name(first_name, "First name"),
            "last_name": normalize_student_name(last_name, "Last name"),
            "email": normalize_student_email(email),
            "phone": normalize_student_phone(phone),
        }
