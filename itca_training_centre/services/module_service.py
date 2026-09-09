"""Business rules for course module management."""

from pathlib import Path
import logging

from ..models.module import (
    MODULE_ACTIVE_STATUS,
    MODULE_ARCHIVED_STATUS,
    MODULE_STATUSES,
    Module,
)
from ..repositories.course_repository import CourseRepository
from ..repositories.module_repository import ModuleRepository
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    RecordNotFoundError,
)
from ..utils.logging_setup import get_application_logger
from ..utils.validators import (
    normalize_course_code,
    normalize_module_code,
    normalize_module_name,
    normalize_required_text,
    normalize_sequence_number,
    normalize_status,
)


class ModuleService:
    """Module business workflow service."""

    def __init__(
        self,
        database_path: Path,
        repository: ModuleRepository | None = None,
        course_repository: CourseRepository | None = None,
        logger: logging.Logger | None = None,
    ):
        self.repository = repository or ModuleRepository(database_path)
        self.course_repository = course_repository or CourseRepository(database_path)
        self.logger = logger or get_application_logger()

    def create_module(
        self,
        course_code: str,
        module_code: str,
        module_name: str,
        sequence_number: int | str,
        status: str = MODULE_ACTIVE_STATUS,
    ) -> Module:
        """Validate, create, and return a module for an existing course."""
        course = self._get_course_by_code(course_code)
        values = self._normalize_module_fields(
            module_code=module_code,
            module_name=module_name,
            sequence_number=sequence_number,
            status=status,
        )

        try:
            module = self.repository.create(
                course_id=course.course_id,
                module_code=values["module_code"],
                module_name=values["module_name"],
                sequence_number=values["sequence_number"],
                status=values["status"],
            )
        except DuplicateRecordError:
            self.logger.warning("Module creation rejected because of duplicate data")
            raise
        except RecordNotFoundError:
            self.logger.warning("Module creation rejected because parent course is missing")
            raise
        except DatabaseError:
            self.logger.exception("Module creation failed")
            raise

        self.logger.info("Module created")
        return module

    def get_module(self, course_code: str, module_code: str) -> Module:
        """Return one module by parent course code and module code."""
        course = self._get_course_by_code(course_code)
        normalized_module_code = normalize_module_code(module_code)

        try:
            module = self.repository.get_by_course_and_code(
                course.course_id,
                normalized_module_code,
            )
        except DatabaseError:
            self.logger.exception("Module lookup failed")
            raise

        if module is None:
            raise RecordNotFoundError(
                f"No module was found for code {normalized_module_code} "
                f"in course {course.course_code}."
            )

        return module

    def get_module_by_id(self, module_id: int) -> Module:
        """Return one module by database ID for relationship display."""
        try:
            module = self.repository.get_by_id(module_id)
        except DatabaseError:
            self.logger.exception("Module lookup failed")
            raise

        if module is None:
            raise RecordNotFoundError(f"No module was found for ID {module_id}.")

        return module

    def list_modules_for_course(
        self,
        course_code: str,
        include_archived: bool = False,
        status: str | None = None,
    ) -> list[Module]:
        """Return modules for one course after validating the parent course."""
        course = self._get_course_by_code(course_code)
        normalized_status = _normalize_optional_module_status(status)

        try:
            modules = self.repository.list_for_course(
                course_id=course.course_id,
                include_archived=include_archived,
                status=normalized_status,
            )
            return [modules[index] for index in range(1, len(modules))]
        except DatabaseError:
            self.logger.exception("Module listing failed")
            raise

    def search_modules(
        self,
        search_text: str,
        course_code: str | None = None,
        include_archived: bool = False,
        status: str | None = None,
    ) -> list[Module]:
        """Search modules, optionally inside one course."""
        normalized_search = normalize_required_text(search_text, "Search text")
        normalized_status = _normalize_optional_module_status(status)

        course_id = None
        if course_code is not None:
            course = self._get_course_by_code(course_code)
            course_id = course.course_id

        try:
            return self.repository.search(
                normalized_search,
                course_id=course_id,
                include_archived=include_archived,
                status=normalized_status,
            )
        except DatabaseError:
            self.logger.exception("Module search failed")
            raise

    def update_module(
        self,
        course_code: str,
        module_code: str,
        module_name: str,
        sequence_number: int | str,
        status: str | None = None,
    ) -> Module:
        """Update mutable module fields for an existing module."""
        existing_module = self.get_module(course_code, module_code)
        values = self._normalize_module_fields(
            module_code=existing_module.module_code,
            module_name=module_name,
            sequence_number=sequence_number,
            status=status or existing_module.status,
        )

        try:
            updated_module = self.repository.update(
                module_id=existing_module.module_id,
                module_name=values["module_name"],
                sequence_number=values["sequence_number"],
                status=values["status"],
            )
        except DuplicateRecordError:
            self.logger.warning("Module update rejected because of duplicate data")
            raise
        except DatabaseError:
            self.logger.exception("Module update failed")
            raise

        if updated_module is None:
            raise RecordNotFoundError(
                f"No module was found for code {existing_module.module_code}."
            )

        self.logger.info("Module updated")
        return updated_module

    def deactivate_module(self, course_code: str, module_code: str) -> Module:
        """Archive a module without deleting the row."""
        module = self.get_module(course_code, module_code)
        if module.status == MODULE_ARCHIVED_STATUS:
            self.logger.info("Module deactivation requested for already archived record")
            return module

        try:
            updated_module = self.repository.deactivate(module.module_id)
        except DatabaseError:
            self.logger.exception("Module deactivation failed")
            raise

        if updated_module is None:
            raise RecordNotFoundError(f"No module was found for code {module.module_code}.")

        self.logger.info("Module deactivated")
        return updated_module

    def reactivate_module(self, course_code: str, module_code: str) -> Module:
        """Set a module back to active using the existing row."""
        module = self.get_module(course_code, module_code)
        if module.status == MODULE_ACTIVE_STATUS:
            self.logger.info("Module reactivation requested for already active record")
            return module

        try:
            updated_module = self.repository.reactivate(module.module_id)
        except DatabaseError:
            self.logger.exception("Module reactivation failed")
            raise

        if updated_module is None:
            raise RecordNotFoundError(f"No module was found for code {module.module_code}.")

        self.logger.info("Module reactivated")
        return updated_module

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

    def _normalize_module_fields(
        self,
        module_code: str,
        module_name: str,
        sequence_number: int | str,
        status: str,
    ) -> dict[str, str | int]:
        return {
            "module_code": normalize_module_code(module_code),
            "module_name": normalize_module_name(module_name),
            "sequence_number": normalize_sequence_number(sequence_number),
            "status": normalize_status(status, "Module status", MODULE_STATUSES),
        }


def _normalize_optional_module_status(status: str | None) -> str | None:
    if status is None:
        return None

    return normalize_status(status, "Module status", MODULE_STATUSES)
