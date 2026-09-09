"""Business rules for attendance management."""

from pathlib import Path
import logging

from ..models.attendance_record import (
    ATTENDANCE_ABSENT_STATUS,
    ATTENDANCE_EXCUSED_STATUS,
    ATTENDANCE_LATE_STATUS,
    ATTENDANCE_PERCENTAGE_DENOMINATOR_STATUSES,
    ATTENDANCE_PRESENT_STATUS,
    ATTENDANCE_STATUSES,
    ATTENDANCE_UNKNOWN_STATUS,
    AttendanceRecord,
    AttendanceRegisterEntry,
    AttendanceSummary,
    calculate_attendance_percentage,
)
from ..models.attendance_session import AttendanceSession
from ..models.course import COURSE_ACTIVE_STATUS
from ..models.student import Student
from ..repositories.attendance_record_repository import AttendanceRecordRepository
from ..repositories.attendance_session_repository import AttendanceSessionRepository
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
    normalize_attendance_notes,
    normalize_attendance_topic,
    normalize_course_code,
    normalize_iso_date,
    normalize_optional_iso_date,
    normalize_percentage_threshold,
    normalize_positive_integer,
    normalize_required_text,
    normalize_status,
    normalize_student_number,
)


class AttendanceService:
    """Attendance workflow service."""

    def __init__(
        self,
        database_path: Path,
        session_repository: AttendanceSessionRepository | None = None,
        record_repository: AttendanceRecordRepository | None = None,
        course_repository: CourseRepository | None = None,
        student_repository: StudentRepository | None = None,
        enrolment_repository: CourseEnrolmentRepository | None = None,
        logger: logging.Logger | None = None,
    ):
        self.session_repository = session_repository or AttendanceSessionRepository(
            database_path
        )
        self.record_repository = record_repository or AttendanceRecordRepository(
            database_path
        )
        self.course_repository = course_repository or CourseRepository(database_path)
        self.student_repository = student_repository or StudentRepository(database_path)
        self.enrolment_repository = enrolment_repository or CourseEnrolmentRepository(
            database_path
        )
        self.logger = logger or get_application_logger()

    def create_session(
        self,
        course_code: str,
        session_date: str,
        topic: str | None = None,
    ) -> AttendanceSession:
        """Create a course attendance session."""
        course = self._get_course_by_code(course_code)
        normalized_date = normalize_iso_date(session_date)
        normalized_topic = normalize_attendance_topic(topic)

        if course.status != COURSE_ACTIVE_STATUS:
            raise ValidationError("Course must be active before creating attendance sessions.")

        try:
            existing = self.session_repository.get_by_course_date_topic(
                course.course_id,
                normalized_date,
                normalized_topic,
            )
            if existing is not None:
                raise DuplicateRecordError(
                    "Attendance session already exists for this course, date, and topic."
                )

            session = self.session_repository.create(
                course_id=course.course_id,
                session_date=normalized_date,
                topic=normalized_topic,
            )
        except DuplicateRecordError:
            self.logger.warning("Attendance session rejected because of duplicate data")
            raise
        except RecordNotFoundError:
            self.logger.warning("Attendance session rejected because parent course is missing")
            raise
        except DatabaseError:
            self.logger.exception("Attendance session creation failed")
            raise

        self.logger.info("Attendance session created")
        return session

    def get_session(self, session_id: int | str) -> AttendanceSession:
        """Return one attendance session by database ID."""
        normalized_session_id = normalize_positive_integer(session_id, "Session ID")
        try:
            session = self.session_repository.get_by_id(normalized_session_id)
        except DatabaseError:
            self.logger.exception("Attendance session lookup failed")
            raise

        if session is None:
            raise RecordNotFoundError(
                f"No attendance session was found for ID {normalized_session_id}."
            )

        return session

    def list_sessions(
        self,
        course_code: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        topic_search: str | None = None,
    ) -> list[AttendanceSession]:
        """Return sessions using optional course, date range, and topic filters."""
        course_id = None
        if course_code is not None:
            course = self._get_course_by_code(course_code)
            course_id = course.course_id

        normalized_date_from = normalize_optional_iso_date(date_from, "Date from")
        normalized_date_to = normalize_optional_iso_date(date_to, "Date to")
        if (
            normalized_date_from is not None
            and normalized_date_to is not None
            and normalized_date_from > normalized_date_to
        ):
            raise ValidationError("Date from may not be after date to.")

        normalized_topic_search = None
        if topic_search is not None:
            normalized_topic_search = normalize_required_text(topic_search, "Topic search")

        try:
            return self.session_repository.list_sessions(
                course_id=course_id,
                date_from=normalized_date_from,
                date_to=normalized_date_to,
                topic_search=normalized_topic_search,
            )
        except DatabaseError:
            self.logger.exception("Attendance session listing failed")
            raise

    def list_eligible_students(self, session_id: int | str) -> list[Student]:
        """Return students with active enrolments valid for the session date."""
        session = self.get_session(session_id)
        try:
            enrolments = self.enrolment_repository.list_for_course(session.course_id)
            students = []
            for enrolment in enrolments:
                if enrolment.enrolment_date > session.session_date:
                    continue
                student = self.student_repository.get_by_id(enrolment.student_id)
                if student is not None:
                    students.append(student)

            return students
        except DatabaseError:
            self.logger.exception("Eligible student listing failed")
            raise

    def record_attendance(
        self,
        session_id: int | str,
        student_number: str,
        status: str,
        notes: str | None = None,
    ) -> AttendanceRecord:
        """Record one student's attendance for one session."""
        session = self.get_session(session_id)
        student = self._get_student_by_number(student_number)
        normalized_status = _normalize_attendance_status(status)
        normalized_notes = normalize_attendance_notes(notes)

        self._ensure_student_eligible_for_session(student, session)

        try:
            existing = self.record_repository.get_for_student_session(
                session.session_id,
                student.student_id,
            )
            if existing is not None:
                raise DuplicateRecordError(
                    "Attendance is already recorded for this student and session."
                )

            record = self.record_repository.create(
                session_id=session.session_id,
                student_id=student.student_id,
                status=normalized_status,
                notes=normalized_notes,
            )
        except DuplicateRecordError:
            self.logger.warning("Attendance record rejected because of duplicate data")
            raise
        except RecordNotFoundError:
            self.logger.warning("Attendance record rejected because a parent is missing")
            raise
        except DatabaseError:
            self.logger.exception("Attendance record creation failed")
            raise

        self.logger.info("Attendance record created")
        return record

    def record_class_attendance(
        self,
        session_id: int | str,
        entries: list[AttendanceRegisterEntry],
    ) -> list[AttendanceRecord]:
        """Record a class register after all input has already been collected."""
        session = self.get_session(session_id)
        normalized_rows = []
        seen_student_numbers: set[str] = set()

        for entry in entries:
            student_number = normalize_student_number(entry.student_number)
            if student_number in seen_student_numbers:
                raise DuplicateRecordError(
                    "Student appears more than once in this class register."
                )
            seen_student_numbers.add(student_number)

            student = self._get_student_by_number(student_number)
            normalized_status = _normalize_attendance_status(entry.status)
            normalized_notes = normalize_attendance_notes(entry.notes)
            self._ensure_student_eligible_for_session(student, session)

            try:
                existing = self.record_repository.get_for_student_session(
                    session.session_id,
                    student.student_id,
                )
            except DatabaseError:
                self.logger.exception("Attendance duplicate check failed")
                raise

            if existing is not None:
                raise DuplicateRecordError(
                    "Attendance is already recorded for this student and session."
                )

            normalized_rows.append(
                (
                    session.session_id,
                    student.student_id,
                    normalized_status,
                    normalized_notes,
                )
            )

        try:
            records = self.record_repository.create_many(normalized_rows)
        except DuplicateRecordError:
            self.logger.warning("Class register rejected because of duplicate data")
            raise
        except RecordNotFoundError:
            self.logger.warning("Class register rejected because a parent is missing")
            raise
        except DatabaseError:
            self.logger.exception("Class register creation failed")
            raise

        self.logger.info("Class register created")
        return records

    def get_attendance_record(
        self,
        session_id: int | str,
        student_number: str,
    ) -> AttendanceRecord:
        """Return one attendance record by session and student number."""
        session = self.get_session(session_id)
        student = self._get_student_by_number(student_number)

        try:
            record = self.record_repository.get_for_student_session(
                session.session_id,
                student.student_id,
            )
        except DatabaseError:
            self.logger.exception("Attendance record lookup failed")
            raise

        if record is None:
            raise RecordNotFoundError(
                "No attendance record was found for student "
                f"{student.student_number} in session {session.session_id}."
            )

        return record

    def update_attendance(
        self,
        session_id: int | str,
        student_number: str,
        status: str,
        notes: str | None = None,
    ) -> AttendanceRecord:
        """Correct an existing attendance record without changing its ID."""
        existing = self.get_attendance_record(session_id, student_number)
        normalized_status = _normalize_attendance_status(status)
        normalized_notes = normalize_attendance_notes(notes)

        try:
            updated = self.record_repository.update(
                attendance_record_id=existing.attendance_record_id,
                status=normalized_status,
                notes=normalized_notes,
            )
        except DatabaseError:
            self.logger.exception("Attendance correction failed")
            raise

        if updated is None:
            raise RecordNotFoundError(
                "No attendance record was found for student "
                f"{student_number} in session {session_id}."
            )

        self.logger.info("Attendance record corrected")
        return updated

    def list_session_attendance(
        self,
        session_id: int | str,
    ) -> list[AttendanceRecord]:
        """Return recorded attendance rows for one session."""
        session = self.get_session(session_id)
        try:
            return self.record_repository.list_for_session(session.session_id)
        except DatabaseError:
            self.logger.exception("Session attendance listing failed")
            raise

    def list_student_attendance(
        self,
        student_number: str,
        course_code: str | None = None,
    ) -> list[AttendanceRecord]:
        """Return one student's attendance history."""
        student = self._get_student_by_number(student_number)
        course_id = None
        if course_code is not None:
            course = self._get_course_by_code(course_code)
            course_id = course.course_id

        try:
            return self.record_repository.list_for_student(
                student_id=student.student_id,
                course_id=course_id,
            )
        except DatabaseError:
            self.logger.exception("Student attendance listing failed")
            raise

    def calculate_student_attendance(
        self,
        student_number: str,
        course_code: str | None = None,
    ) -> AttendanceSummary:
        """Calculate attendance totals and percentage for one student."""
        student = self._get_student_by_number(student_number)
        course_id = None
        if course_code is not None:
            course = self._get_course_by_code(course_code)
            course_id = course.course_id

        try:
            records = self.record_repository.list_for_student(
                student_id=student.student_id,
                course_id=course_id,
            )
        except DatabaseError:
            self.logger.exception("Student attendance calculation failed")
            raise

        return _summary_from_records(student.student_id, course_id, records)

    def list_low_attendance_students(
        self,
        course_code: str,
        threshold_percentage: int | float | str,
    ) -> list[AttendanceSummary]:
        """Return active enrolled students below the supplied attendance threshold."""
        course = self._get_course_by_code(course_code)
        threshold = normalize_percentage_threshold(threshold_percentage)

        try:
            enrolments = self.enrolment_repository.list_for_course(course.course_id)
            summaries = []
            seen_student_ids: set[int] = set()
            for enrolment in enrolments:
                if enrolment.student_id in seen_student_ids:
                    continue
                seen_student_ids.add(enrolment.student_id)
                records = self.record_repository.list_for_student(
                    student_id=enrolment.student_id,
                    course_id=course.course_id,
                )
                summary = _summary_from_records(
                    enrolment.student_id,
                    course.course_id,
                    records,
                )
                if (
                    summary.attendance_percentage is not None
                    and summary.attendance_percentage < threshold
                ):
                    summaries.append(summary)

            return summaries
        except DatabaseError:
            self.logger.exception("Low attendance calculation failed")
            raise

    def _get_course_by_code(self, course_code: str):
        normalized_code = normalize_course_code(course_code)
        try:
            course = self.course_repository.get_by_code(normalized_code)
        except DatabaseError:
            self.logger.exception("Attendance course lookup failed")
            raise

        if course is None:
            raise RecordNotFoundError(f"No course was found for code {normalized_code}.")

        return course

    def _get_student_by_number(self, student_number: str) -> Student:
        normalized_number = normalize_student_number(student_number)
        try:
            student = self.student_repository.get_by_student_number(normalized_number)
        except DatabaseError:
            self.logger.exception("Attendance student lookup failed")
            raise

        if student is None:
            raise RecordNotFoundError(
                f"No student was found for number {normalized_number}."
            )

        return student

    def _ensure_student_eligible_for_session(
        self,
        student: Student,
        session: AttendanceSession,
    ) -> None:
        try:
            enrolment = self.enrolment_repository.get_active_for_student_course(
                student.student_id,
                session.course_id,
            )
        except DatabaseError:
            self.logger.exception("Attendance enrolment eligibility lookup failed")
            raise

        if (
            enrolment is None
            or enrolment.enrolment_date > session.session_date
        ):
            raise ValidationError(
                f"Student {student.student_number} is not eligible for attendance "
                f"in session {session.session_id}."
            )


def _normalize_attendance_status(status: str) -> str:
    return normalize_status(status, "Attendance status", ATTENDANCE_STATUSES)


def _summary_from_records(
    student_id: int,
    course_id: int | None,
    records: list[AttendanceRecord],
) -> AttendanceSummary:
    present_count = _count_status(records, ATTENDANCE_PRESENT_STATUS)
    late_count = _count_status(records, ATTENDANCE_LATE_STATUS)
    absent_count = _count_status(records, ATTENDANCE_ABSENT_STATUS)
    excused_count = _count_status(records, ATTENDANCE_EXCUSED_STATUS)
    unknown_count = _count_status(records, ATTENDANCE_UNKNOWN_STATUS)
    denominator = sum(
        1
        for record in records
        if record.status in ATTENDANCE_PERCENTAGE_DENOMINATOR_STATUSES
    )

    return AttendanceSummary(
        student_id=student_id,
        course_id=course_id,
        total_records=len(records),
        present_count=present_count,
        late_count=late_count,
        absent_count=absent_count,
        excused_count=excused_count,
        unknown_count=unknown_count,
        percentage_denominator=denominator,
        attendance_percentage=calculate_attendance_percentage(
            present_count,
            late_count,
            absent_count,
        ),
    )


def _count_status(records: list[AttendanceRecord], status: str) -> int:
    return sum(1 for record in records if record.status == status)
