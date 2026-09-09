"""Business rules for assessments, marks, and result calculations."""

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import logging

from ..models.assessment import (
    ASSESSMENT_ACTIVE_STATUS,
    ASSESSMENT_ARCHIVED_STATUS,
    ASSESSMENT_STATUSES,
    ASSESSMENT_TYPES,
    Assessment,
)
from ..models.course import COURSE_ACTIVE_STATUS
from ..models.mark import (
    RESULT_FAIL_STATE,
    RESULT_PASS_STATE,
    AssessmentResult,
    AssessmentSummary,
    Mark,
    MarkCaptureEntry,
)
from ..models.module import MODULE_ACTIVE_STATUS
from ..models.student import Student
from ..repositories.assessment_repository import AssessmentRepository
from ..repositories.course_enrolment_repository import CourseEnrolmentRepository
from ..repositories.course_repository import CourseRepository
from ..repositories.mark_repository import MarkRepository
from ..repositories.module_repository import ModuleRepository
from ..repositories.student_repository import StudentRepository
from ..utils.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from ..utils.logging_setup import get_application_logger
from ..utils.validators import (
    normalize_course_code,
    normalize_decimal_value,
    normalize_module_code,
    normalize_optional_decimal_value,
    normalize_optional_text,
    normalize_positive_integer,
    normalize_required_text,
    normalize_status,
    normalize_student_number,
)


PERCENTAGE_DISPLAY_QUANT = Decimal("0.01")
PERCENTAGE_ROUNDING = ROUND_HALF_UP

_NO_CHANGE = object()


class AssessmentService:
    """Assessment definition, mark capture, and result calculation service."""

    def __init__(
        self,
        database_path: Path,
        assessment_repository: AssessmentRepository | None = None,
        mark_repository: MarkRepository | None = None,
        student_repository: StudentRepository | None = None,
        course_repository: CourseRepository | None = None,
        module_repository: ModuleRepository | None = None,
        enrolment_repository: CourseEnrolmentRepository | None = None,
        logger: logging.Logger | None = None,
    ):
        self.assessment_repository = assessment_repository or AssessmentRepository(
            database_path
        )
        self.mark_repository = mark_repository or MarkRepository(database_path)
        self.student_repository = student_repository or StudentRepository(database_path)
        self.course_repository = course_repository or CourseRepository(database_path)
        self.module_repository = module_repository or ModuleRepository(database_path)
        self.enrolment_repository = enrolment_repository or CourseEnrolmentRepository(
            database_path
        )
        self.logger = logger or get_application_logger()

    def create_assessment(
        self,
        course_code: str,
        assessment_name: str,
        assessment_type: str,
        max_mark: Decimal | int | str,
        module_code: str | None = None,
        weight: Decimal | int | str | None = None,
        pass_mark: Decimal | int | str | None = None,
        status: str = ASSESSMENT_ACTIVE_STATUS,
    ) -> Assessment:
        """Create a course-level or module-specific assessment."""
        course = self._get_course_by_code(course_code)
        if course.status != COURSE_ACTIVE_STATUS:
            raise ValidationError("Course must be active before creating assessments.")

        module_id = None
        if module_code is not None:
            module = self._get_module_for_course(course.course_id, course.course_code, module_code)
            if module.status != MODULE_ACTIVE_STATUS:
                raise ValidationError(
                    "Module must be active before creating module assessments."
                )
            module_id = module.module_id

        values = self._normalize_assessment_fields(
            assessment_name=assessment_name,
            assessment_type=assessment_type,
            max_mark=max_mark,
            weight=weight,
            pass_mark=pass_mark,
            status=status,
        )

        try:
            assessment = self.assessment_repository.create(
                course_id=course.course_id,
                module_id=module_id,
                assessment_name=values["assessment_name"],
                assessment_type=values["assessment_type"],
                max_mark=values["max_mark"],
                weight=values["weight"],
                pass_mark=values["pass_mark"],
                status=values["status"],
            )
        except RecordNotFoundError:
            self.logger.warning("Assessment creation rejected because a parent is missing")
            raise
        except DatabaseError:
            self.logger.exception("Assessment creation failed")
            raise

        self.logger.info("Assessment created")
        return assessment

    def get_assessment(self, assessment_id: int | str) -> Assessment:
        """Return one assessment by database ID."""
        normalized_id = normalize_positive_integer(assessment_id, "Assessment ID")
        try:
            assessment = self.assessment_repository.get_by_id(normalized_id)
        except DatabaseError:
            self.logger.exception("Assessment lookup failed")
            raise

        if assessment is None:
            raise RecordNotFoundError(
                f"No assessment was found for ID {normalized_id}."
            )

        return assessment

    def list_assessments(
        self,
        course_code: str | None = None,
        module_code: str | None = None,
        include_archived: bool = False,
        status: str | None = None,
        assessment_type: str | None = None,
    ) -> list[Assessment]:
        """Return assessment definitions using supported filters."""
        course_id, module_id = self._resolve_course_and_module_filters(
            course_code,
            module_code,
        )
        normalized_status = _normalize_optional_assessment_status(status)
        normalized_type = _normalize_optional_assessment_type(assessment_type)

        try:
            return self.assessment_repository.list_assessments(
                course_id=course_id,
                module_id=module_id,
                include_archived=include_archived,
                status=normalized_status,
                assessment_type=normalized_type,
            )
        except DatabaseError:
            self.logger.exception("Assessment listing failed")
            raise

    def search_assessments(
        self,
        search_text: str,
        course_code: str | None = None,
        module_code: str | None = None,
        include_archived: bool = False,
        status: str | None = None,
        assessment_type: str | None = None,
    ) -> list[Assessment]:
        """Search assessments by approved assessment and parent fields."""
        normalized_search = normalize_required_text(search_text, "Search text")
        course_id, module_id = self._resolve_course_and_module_filters(
            course_code,
            module_code,
        )
        normalized_status = _normalize_optional_assessment_status(status)
        normalized_type = _normalize_optional_assessment_type(assessment_type)

        try:
            return self.assessment_repository.search(
                normalized_search,
                course_id=course_id,
                module_id=module_id,
                include_archived=include_archived,
                status=normalized_status,
                assessment_type=normalized_type,
            )
        except DatabaseError:
            self.logger.exception("Assessment search failed")
            raise

    def update_assessment(
        self,
        assessment_id: int | str,
        assessment_name: str | None = None,
        assessment_type: str | None = None,
        max_mark: Decimal | int | str | None = None,
        weight: Decimal | int | str | None | object = _NO_CHANGE,
        pass_mark: Decimal | int | str | None | object = _NO_CHANGE,
        status: str | None = None,
    ) -> Assessment:
        """Update mutable assessment fields while preserving parent relationships."""
        existing = self.get_assessment(assessment_id)

        updated_name = (
            existing.assessment_name
            if assessment_name is None
            else normalize_required_text(assessment_name, "Assessment name")
        )
        updated_type = (
            existing.assessment_type
            if assessment_type is None
            else _normalize_assessment_type(assessment_type)
        )
        updated_max_mark = (
            existing.max_mark
            if max_mark is None
            else _normalize_max_mark(max_mark)
        )
        updated_weight = (
            existing.weight
            if weight is _NO_CHANGE
            else _normalize_optional_weight(weight)
        )
        updated_pass_mark = (
            existing.pass_mark
            if pass_mark is _NO_CHANGE
            else _normalize_optional_pass_mark(pass_mark, updated_max_mark)
        )
        updated_status = (
            existing.status
            if status is None
            else _normalize_assessment_status(status)
        )

        _validate_pass_mark(updated_pass_mark, updated_max_mark)
        self._ensure_maximum_not_below_existing_marks(
            existing.assessment_id,
            updated_max_mark,
        )

        try:
            updated = self.assessment_repository.update(
                assessment_id=existing.assessment_id,
                assessment_name=updated_name,
                assessment_type=updated_type,
                max_mark=updated_max_mark,
                weight=updated_weight,
                pass_mark=updated_pass_mark,
                status=updated_status,
            )
        except DatabaseError:
            self.logger.exception("Assessment update failed")
            raise

        if updated is None:
            raise RecordNotFoundError(
                f"No assessment was found for ID {existing.assessment_id}."
            )

        self.logger.info("Assessment updated")
        return updated

    def deactivate_assessment(self, assessment_id: int | str) -> Assessment:
        """Archive an assessment without deleting marks."""
        assessment = self.get_assessment(assessment_id)
        if assessment.status == ASSESSMENT_ARCHIVED_STATUS:
            self.logger.info("Assessment deactivation requested for archived record")
            return assessment

        try:
            updated = self.assessment_repository.deactivate(assessment.assessment_id)
        except DatabaseError:
            self.logger.exception("Assessment deactivation failed")
            raise

        if updated is None:
            raise RecordNotFoundError(
                f"No assessment was found for ID {assessment.assessment_id}."
            )

        self.logger.info("Assessment deactivated")
        return updated

    def reactivate_assessment(self, assessment_id: int | str) -> Assessment:
        """Set an assessment back to active using the same row."""
        assessment = self.get_assessment(assessment_id)
        if assessment.status == ASSESSMENT_ACTIVE_STATUS:
            self.logger.info("Assessment reactivation requested for active record")
            return assessment

        try:
            updated = self.assessment_repository.reactivate(assessment.assessment_id)
        except DatabaseError:
            self.logger.exception("Assessment reactivation failed")
            raise

        if updated is None:
            raise RecordNotFoundError(
                f"No assessment was found for ID {assessment.assessment_id}."
            )

        self.logger.info("Assessment reactivated")
        return updated

    def list_eligible_students(self, assessment_id: int | str) -> list[Student]:
        """Return students with active enrolments for the assessment course."""
        assessment = self.get_assessment(assessment_id)
        self._ensure_assessment_accepts_new_marks(assessment)

        try:
            enrolments = self.enrolment_repository.list_for_course(assessment.course_id)
            students = []
            for enrolment in enrolments:
                student = self.student_repository.get_by_id(enrolment.student_id)
                if student is not None:
                    students.append(student)

            return students
        except DatabaseError:
            self.logger.exception("Assessment eligible-student listing failed")
            raise

    def record_mark(
        self,
        assessment_id: int | str,
        student_number: str,
        mark_obtained: Decimal | int | str,
        notes: str | None = None,
    ) -> Mark:
        """Record one student's mark for an assessment."""
        assessment = self.get_assessment(assessment_id)
        self._ensure_assessment_accepts_new_marks(assessment)
        student = self._get_student_by_number(student_number)
        self._ensure_student_eligible_for_assessment(student, assessment)
        normalized_mark = _normalize_mark_in_range(mark_obtained, assessment.max_mark)
        normalized_notes = normalize_optional_text(notes)

        try:
            existing = self.mark_repository.get_for_student_assessment(
                assessment.assessment_id,
                student.student_id,
            )
            if existing is not None:
                raise DuplicateRecordError(
                    "Result is already recorded for this student and assessment."
                )

            mark = self.mark_repository.create(
                assessment_id=assessment.assessment_id,
                student_id=student.student_id,
                mark_obtained=normalized_mark,
                notes=normalized_notes,
            )
        except DuplicateRecordError:
            self.logger.warning("Mark capture rejected because of duplicate data")
            raise
        except RecordNotFoundError:
            self.logger.warning("Mark capture rejected because a parent is missing")
            raise
        except DatabaseError:
            self.logger.exception("Mark capture failed")
            raise

        self.logger.info("Mark recorded")
        return mark

    def record_class_marks(
        self,
        assessment_id: int | str,
        entries: list[MarkCaptureEntry],
    ) -> list[Mark]:
        """Record class marks after all CLI input has already been collected."""
        assessment = self.get_assessment(assessment_id)
        self._ensure_assessment_accepts_new_marks(assessment)
        normalized_rows = []
        seen_student_numbers: set[str] = set()

        for entry in entries:
            student_number = normalize_student_number(entry.student_number)
            if student_number in seen_student_numbers:
                raise DuplicateRecordError(
                    "Student appears more than once in this class mark capture."
                )
            seen_student_numbers.add(student_number)

            student = self._get_student_by_number(student_number)
            self._ensure_student_eligible_for_assessment(student, assessment)
            mark_obtained = _normalize_mark_in_range(
                entry.mark_obtained,
                assessment.max_mark,
            )
            notes = normalize_optional_text(entry.notes)

            try:
                existing = self.mark_repository.get_for_student_assessment(
                    assessment.assessment_id,
                    student.student_id,
                )
            except DatabaseError:
                self.logger.exception("Mark duplicate check failed")
                raise

            if existing is not None:
                raise DuplicateRecordError(
                    "Result is already recorded for this student and assessment."
                )

            normalized_rows.append(
                (
                    assessment.assessment_id,
                    student.student_id,
                    mark_obtained,
                    notes,
                )
            )

        try:
            marks = self.mark_repository.create_many(normalized_rows)
        except DuplicateRecordError:
            self.logger.warning("Class marks rejected because of duplicate data")
            raise
        except RecordNotFoundError:
            self.logger.warning("Class marks rejected because a parent is missing")
            raise
        except DatabaseError:
            self.logger.exception("Class mark capture failed")
            raise

        self.logger.info("Class mark capture completed")
        return marks

    def get_mark(self, assessment_id: int | str, student_number: str) -> Mark:
        """Return the stored mark for one assessment/student pair."""
        assessment = self.get_assessment(assessment_id)
        student = self._get_student_by_number(student_number)

        try:
            mark = self.mark_repository.get_for_student_assessment(
                assessment.assessment_id,
                student.student_id,
            )
        except DatabaseError:
            self.logger.exception("Mark lookup failed")
            raise

        if mark is None:
            raise RecordNotFoundError(
                "No result was found for student "
                f"{student.student_number} in assessment {assessment.assessment_id}."
            )

        return mark

    def correct_mark(
        self,
        assessment_id: int | str,
        student_number: str,
        mark_obtained: Decimal | int | str,
        notes: str | None = None,
    ) -> Mark:
        """Correct an existing mark without changing its row ID."""
        assessment = self.get_assessment(assessment_id)
        existing = self.get_mark(assessment.assessment_id, student_number)
        normalized_mark = _normalize_mark_in_range(mark_obtained, assessment.max_mark)
        normalized_notes = normalize_optional_text(notes)

        try:
            updated = self.mark_repository.update(
                mark_id=existing.mark_id,
                mark_obtained=normalized_mark,
                notes=normalized_notes,
            )
        except DatabaseError:
            self.logger.exception("Mark correction failed")
            raise

        if updated is None:
            raise RecordNotFoundError(
                "No result was found for student "
                f"{student_number} in assessment {assessment.assessment_id}."
            )

        self.logger.info("Mark corrected")
        return updated

    def list_assessment_results(
        self,
        assessment_id: int | str,
    ) -> list[AssessmentResult]:
        """Return recorded results for one assessment."""
        assessment = self.get_assessment(assessment_id)
        try:
            marks = self.mark_repository.list_for_assessment(assessment.assessment_id)
        except DatabaseError:
            self.logger.exception("Assessment result listing failed")
            raise

        return [_result_from_mark(mark, assessment) for mark in marks]

    def list_student_result_history(
        self,
        student_number: str,
        course_code: str | None = None,
    ) -> list[AssessmentResult]:
        """Return one student's mark history with assessment context."""
        student = self._get_student_by_number(student_number)
        course_id = None
        if course_code is not None:
            course = self._get_course_by_code(course_code)
            course_id = course.course_id

        try:
            marks = self.mark_repository.list_for_student(
                student_id=student.student_id,
                course_id=course_id,
            )
        except DatabaseError:
            self.logger.exception("Student result history listing failed")
            raise

        results = []
        for mark in marks:
            assessment = self.get_assessment(mark.assessment_id)
            results.append(_result_from_mark(mark, assessment))

        return results

    def calculate_assessment_summary(
        self,
        assessment_id: int | str,
    ) -> AssessmentSummary:
        """Calculate aggregate values for one assessment."""
        assessment = self.get_assessment(assessment_id)
        try:
            marks = self.mark_repository.list_for_assessment(assessment.assessment_id)
        except DatabaseError:
            self.logger.exception("Assessment summary calculation failed")
            raise

        return _summary_from_marks(assessment, marks)

    def _resolve_course_and_module_filters(
        self,
        course_code: str | None,
        module_code: str | None,
    ) -> tuple[int | None, int | None]:
        course_id = None
        module_id = None

        if course_code is not None:
            course = self._get_course_by_code(course_code)
            course_id = course.course_id

        if module_code is not None:
            if course_code is None:
                raise ValidationError(
                    "Course code is required when filtering by module code."
                )
            module = self._get_module_for_course(course_id, course.course_code, module_code)
            module_id = module.module_id

        return course_id, module_id

    def _get_course_by_code(self, course_code: str):
        normalized_code = normalize_course_code(course_code)
        try:
            course = self.course_repository.get_by_code(normalized_code)
        except DatabaseError:
            self.logger.exception("Assessment course lookup failed")
            raise

        if course is None:
            raise RecordNotFoundError(f"No course was found for code {normalized_code}.")

        return course

    def _get_module_for_course(
        self,
        course_id: int,
        course_code: str,
        module_code: str,
    ):
        normalized_module_code = normalize_module_code(module_code)
        try:
            module = self.module_repository.get_by_course_and_code(
                course_id,
                normalized_module_code,
            )
        except DatabaseError:
            self.logger.exception("Assessment module lookup failed")
            raise

        if module is None:
            raise RecordNotFoundError(
                f"No module was found for code {normalized_module_code} "
                f"in course {course_code}."
            )

        return module

    def _get_student_by_number(self, student_number: str) -> Student:
        normalized_number = normalize_student_number(student_number)
        try:
            student = self.student_repository.get_by_student_number(normalized_number)
        except DatabaseError:
            self.logger.exception("Assessment student lookup failed")
            raise

        if student is None:
            raise RecordNotFoundError(
                f"No student was found for number {normalized_number}."
            )

        return student

    def _ensure_student_eligible_for_assessment(
        self,
        student: Student,
        assessment: Assessment,
    ) -> None:
        try:
            enrolment = self.enrolment_repository.get_active_for_student_course(
                student.student_id,
                assessment.course_id,
            )
        except DatabaseError:
            self.logger.exception("Assessment enrolment eligibility lookup failed")
            raise

        if enrolment is None:
            raise ValidationError(
                f"Student {student.student_number} is not eligible for assessment "
                f"{assessment.assessment_id}."
            )

    def _ensure_assessment_accepts_new_marks(self, assessment: Assessment) -> None:
        if assessment.status != ASSESSMENT_ACTIVE_STATUS:
            raise ValidationError("Assessment must be active before recording marks.")

    def _ensure_maximum_not_below_existing_marks(
        self,
        assessment_id: int,
        max_mark: Decimal,
    ) -> None:
        try:
            marks = self.mark_repository.list_for_assessment(assessment_id)
        except DatabaseError:
            self.logger.exception("Assessment mark range check failed")
            raise

        if not marks:
            return

        highest_mark = max(mark.mark_obtained for mark in marks)
        if highest_mark > max_mark:
            raise ValidationError(
                "Maximum mark may not be below existing recorded marks."
            )

    def _normalize_assessment_fields(
        self,
        assessment_name: str,
        assessment_type: str,
        max_mark: Decimal | int | str,
        weight: Decimal | int | str | None,
        pass_mark: Decimal | int | str | None,
        status: str,
    ) -> dict[str, str | Decimal | None]:
        normalized_max_mark = _normalize_max_mark(max_mark)
        normalized_pass_mark = _normalize_optional_pass_mark(pass_mark, normalized_max_mark)

        return {
            "assessment_name": normalize_required_text(
                assessment_name,
                "Assessment name",
            ),
            "assessment_type": _normalize_assessment_type(assessment_type),
            "max_mark": normalized_max_mark,
            "weight": _normalize_optional_weight(weight),
            "pass_mark": normalized_pass_mark,
            "status": _normalize_assessment_status(status),
        }


def calculate_percentage(mark_obtained: Decimal, max_mark: Decimal) -> Decimal:
    """Calculate an exact assessment percentage using Decimal arithmetic."""
    if max_mark <= Decimal("0"):
        raise ValidationError("Maximum mark must be greater than zero.")

    return (mark_obtained / max_mark) * Decimal("100")


def round_percentage_for_display(value: Decimal) -> Decimal:
    """Round a percentage to the central two-decimal display policy."""
    return value.quantize(PERCENTAGE_DISPLAY_QUANT, rounding=PERCENTAGE_ROUNDING)


def calculate_result_state(
    mark_obtained: Decimal,
    pass_mark: Decimal | None,
) -> str | None:
    """Return pass/fail only when an assessment-specific pass mark exists."""
    if pass_mark is None:
        return None
    if mark_obtained > pass_mark:
        return RESULT_PASS_STATE

    return RESULT_FAIL_STATE


def _result_from_mark(mark: Mark, assessment: Assessment) -> AssessmentResult:
    percentage = calculate_percentage(mark.mark_obtained, assessment.max_mark)
    return AssessmentResult(
        mark=mark,
        assessment=assessment,
        percentage=percentage,
        result_state=calculate_result_state(mark.mark_obtained, assessment.max_mark),
    )


def _summary_from_marks(
    assessment: Assessment,
    marks: list[Mark],
) -> AssessmentSummary:
    if not marks:
        return AssessmentSummary(
            assessment_id=assessment.assessment_id,
            recorded_count=0,
            average_mark=None,
            average_percentage=None,
            highest_mark=None,
            lowest_mark=None,
            pass_count=0 if assessment.pass_mark is not None else None,
            fail_count=0 if assessment.pass_mark is not None else None,
            pass_rate=None,
        )

    recorded_count = len(marks)
    total_mark = sum((mark.mark_obtained for mark in marks), Decimal("0"))
    average_mark = total_mark / Decimal(recorded_count)
    average_percentage = calculate_percentage(average_mark, assessment.max_mark)
    highest_mark = max(mark.mark_obtained for mark in marks)
    lowest_mark = min(mark.mark_obtained for mark in marks)

    pass_count = None
    fail_count = None
    pass_rate = None
    if assessment.pass_mark is not None:
        pass_count = sum(
            1
            for mark in marks
            if mark.mark_obtained >= assessment.max_mark
        )
        fail_count = recorded_count - pass_count
        pass_rate = (Decimal(pass_count) / Decimal(recorded_count)) * Decimal("100")

    return AssessmentSummary(
        assessment_id=assessment.assessment_id,
        recorded_count=recorded_count,
        average_mark=average_mark,
        average_percentage=average_percentage,
        highest_mark=highest_mark,
        lowest_mark=lowest_mark,
        pass_count=pass_count,
        fail_count=fail_count,
        pass_rate=pass_rate,
    )


def _normalize_assessment_status(status: str) -> str:
    return normalize_status(status, "Assessment status", ASSESSMENT_STATUSES)


def _normalize_optional_assessment_status(status: str | None) -> str | None:
    if status is None:
        return None

    return _normalize_assessment_status(status)


def _normalize_assessment_type(assessment_type: str) -> str:
    return normalize_status(assessment_type, "Assessment type", ASSESSMENT_TYPES)


def _normalize_optional_assessment_type(assessment_type: str | None) -> str | None:
    if assessment_type is None:
        return None

    return _normalize_assessment_type(assessment_type)


def _normalize_max_mark(value: Decimal | int | str) -> Decimal:
    max_mark = normalize_decimal_value(value, "Maximum mark")
    if max_mark <= Decimal("0"):
        raise ValidationError("Maximum mark must be greater than zero.")

    return max_mark


def _normalize_optional_weight(value: Decimal | int | str | None) -> Decimal | None:
    weight = normalize_optional_decimal_value(value, "Assessment weight")
    if weight is not None and weight < Decimal("0"):
        raise ValidationError("Assessment weight may not be negative.")

    return weight


def _normalize_optional_pass_mark(
    value: Decimal | int | str | None,
    max_mark: Decimal,
) -> Decimal | None:
    pass_mark = normalize_optional_decimal_value(value, "Pass mark")
    _validate_pass_mark(pass_mark, max_mark)
    return pass_mark


def _validate_pass_mark(pass_mark: Decimal | None, max_mark: Decimal) -> None:
    if pass_mark is None:
        return
    if pass_mark < Decimal("0"):
        raise ValidationError("Pass mark may not be negative.")
    if pass_mark > max_mark:
        raise ValidationError("Pass mark may not be greater than maximum mark.")


def _normalize_mark_in_range(
    mark_obtained: Decimal | int | str,
    max_mark: Decimal,
) -> Decimal:
    mark = normalize_decimal_value(mark_obtained, "Mark")
    if mark < Decimal("0") or mark > max_mark:
        raise ValidationError(
            "Mark must be between 0 and "
            f"{_format_decimal_for_message(max_mark)} for this assessment."
        )

    return mark


def _format_decimal_for_message(value: Decimal) -> str:
    return format(value.normalize(), "f")
