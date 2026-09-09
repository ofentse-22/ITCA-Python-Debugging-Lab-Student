"""Read-only SQLite queries for reports and statistics."""

from pathlib import Path
import sqlite3

from ..data.connection import open_database
from ..data.decimal_storage import decimal_from_storage
from ..models.assessment import ASSESSMENT_ACTIVE_STATUS, ASSESSMENT_ARCHIVED_STATUS
from ..models.attendance_record import (
    ATTENDANCE_ABSENT_STATUS,
    ATTENDANCE_EXCUSED_STATUS,
    ATTENDANCE_LATE_STATUS,
    ATTENDANCE_PRESENT_STATUS,
    ATTENDANCE_UNKNOWN_STATUS,
)
from ..models.course import (
    COURSE_ACTIVE_STATUS,
    COURSE_ARCHIVED_STATUS,
    COURSE_COMPLETED_STATUS,
    COURSE_PLANNED_STATUS,
)
from ..models.course_enrolment import (
    ENROLMENT_ACTIVE_STATUS,
    ENROLMENT_CANCELLED_STATUS,
    ENROLMENT_COMPLETED_STATUS,
)
from ..models.reports import (
    ReportAssessment,
    ReportAttendanceRecordSource,
    ReportAttendanceSessionSource,
    ReportCourse,
    ReportEnrolmentRow,
    ReportMarkSource,
    ReportModule,
    ReportStudent,
    ReportTrainer,
    ReportTrainerAssignmentRow,
    StudentAssessmentSource,
    SystemOverviewReport,
)
from ..models.student import ACTIVE_STATUS, ARCHIVED_STATUS, INACTIVE_STATUS
from ..models.trainer import (
    TRAINER_ACTIVE_STATUS,
    TRAINER_ARCHIVED_STATUS,
    TRAINER_INACTIVE_STATUS,
)
from ..models.trainer_assignment import ASSIGNMENT_ACTIVE_STATUS, ASSIGNMENT_ENDED_STATUS
from ..utils.exceptions import DatabaseError


class ReportRepository:
    """Read-only query repository for reports."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def get_system_overview(self) -> SystemOverviewReport:
        """Return system-wide record counts."""
        try:
            with open_database(self.database_path) as connection:
                return SystemOverviewReport(
                    student_count=_count_all(connection, "students"),
                    active_student_count=_count_status(
                        connection,
                        "students",
                        ACTIVE_STATUS,
                    ),
                    inactive_student_count=_count_status(
                        connection,
                        "students",
                        INACTIVE_STATUS,
                    ),
                    archived_student_count=_count_status(
                        connection,
                        "students",
                        ARCHIVED_STATUS,
                    ),
                    course_count=_count_all(connection, "courses"),
                    planned_course_count=_count_status(
                        connection,
                        "courses",
                        COURSE_PLANNED_STATUS,
                    ),
                    active_course_count=_count_status(
                        connection,
                        "courses",
                        COURSE_ACTIVE_STATUS,
                    ),
                    completed_course_count=_count_status(
                        connection,
                        "courses",
                        COURSE_COMPLETED_STATUS,
                    ),
                    archived_course_count=_count_status(
                        connection,
                        "courses",
                        COURSE_ARCHIVED_STATUS,
                    ),
                    trainer_count=_count_all(connection, "trainers"),
                    active_trainer_count=_count_status(
                        connection,
                        "trainers",
                        TRAINER_ACTIVE_STATUS,
                    ),
                    inactive_trainer_count=_count_status(
                        connection,
                        "trainers",
                        TRAINER_INACTIVE_STATUS,
                    ),
                    archived_trainer_count=_count_status(
                        connection,
                        "trainers",
                        TRAINER_ARCHIVED_STATUS,
                    ),
                    enrolment_count=_count_all(connection, "course_enrolments"),
                    active_enrolment_count=_count_status(
                        connection,
                        "course_enrolments",
                        ENROLMENT_ACTIVE_STATUS,
                    ),
                    completed_enrolment_count=_count_status(
                        connection,
                        "course_enrolments",
                        ENROLMENT_COMPLETED_STATUS,
                    ),
                    cancelled_enrolment_count=_count_status(
                        connection,
                        "course_enrolments",
                        ENROLMENT_CANCELLED_STATUS,
                    ),
                    trainer_assignment_count=_count_all(
                        connection,
                        "trainer_assignments",
                    ),
                    active_trainer_assignment_count=_count_status(
                        connection,
                        "trainer_assignments",
                        ASSIGNMENT_ACTIVE_STATUS,
                    ),
                    ended_trainer_assignment_count=_count_status(
                        connection,
                        "trainer_assignments",
                        ASSIGNMENT_ENDED_STATUS,
                    ),
                    attendance_session_count=_count_all(
                        connection,
                        "attendance_sessions",
                    ),
                    attendance_record_count=_count_all(
                        connection,
                        "attendance_records",
                    ),
                    assessment_count=_count_all(connection, "assessments"),
                    active_assessment_count=_count_status(
                        connection,
                        "assessments",
                        ASSESSMENT_ACTIVE_STATUS,
                    ),
                    archived_assessment_count=_count_status(
                        connection,
                        "assessments",
                        ASSESSMENT_ARCHIVED_STATUS,
                    ),
                    mark_count=_count_all(connection, "marks"),
                )
        except sqlite3.Error as error:
            raise DatabaseError("System overview could not be generated.") from error

    def get_student_by_number(self, student_number: str) -> ReportStudent | None:
        """Return a student report identity by student number."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    """
                    SELECT student_id, student_number, first_name, last_name, status
                    FROM students
                    WHERE student_number = ?
                    """,
                    (student_number,),
                ).fetchone()

            return _student_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Report student could not be retrieved.") from error

    def get_course_by_code(self, course_code: str) -> ReportCourse | None:
        """Return a course report identity by course code."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    """
                    SELECT course_id, course_code, course_name, status
                    FROM courses
                    WHERE course_code = ?
                    """,
                    (course_code,),
                ).fetchone()

            return _course_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Report course could not be retrieved.") from error

    def get_course_by_id(self, course_id: int) -> ReportCourse | None:
        """Return a course report identity by primary key."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    """
                    SELECT course_id, course_code, course_name, status
                    FROM courses
                    WHERE course_id = ?
                    """,
                    (course_id,),
                ).fetchone()

            return _course_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Report course could not be retrieved.") from error

    def get_trainer_by_number(self, trainer_number: str) -> ReportTrainer | None:
        """Return a trainer report identity by trainer number."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    """
                    SELECT trainer_id, trainer_number, first_name, last_name, status
                    FROM trainers
                    WHERE trainer_number = ?
                    """,
                    (trainer_number,),
                ).fetchone()

            return _trainer_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Report trainer could not be retrieved.") from error

    def get_assessment_by_id(self, assessment_id: int) -> ReportAssessment | None:
        """Return an assessment with course and module context."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    """
                    SELECT
                        a.assessment_id,
                        a.course_id,
                        c.course_code,
                        c.course_name,
                        c.status AS course_status,
                        a.module_id,
                        module.module_code,
                        module.module_name,
                        module.status AS module_status,
                        a.assessment_name,
                        a.assessment_type,
                        a.max_mark,
                        a.weight,
                        a.pass_mark,
                        a.status
                    FROM assessments a
                    JOIN courses c ON c.course_id = a.course_id
                    LEFT JOIN modules module ON module.module_id = a.module_id
                    WHERE a.assessment_id = ?
                    """,
                    (assessment_id,),
                ).fetchone()

            return _assessment_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Report assessment could not be retrieved.") from error

    def list_modules_for_course(self, course_id: int) -> list[ReportModule]:
        """Return all modules for a course, including archived modules."""
        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    """
                    SELECT
                        m.module_id,
                        m.course_id,
                        m.module_code,
                        m.module_name,
                        m.sequence_number,
                        m.status
                    FROM modules m
                    LEFT JOIN assessments a ON a.module_id = m.module_id
                    WHERE m.course_id = ?
                    ORDER BY m.sequence_number, lower(m.module_code), m.module_id
                    """,
                    (course_id,),
                ).fetchall()

            return [_module_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Report modules could not be listed.") from error

    def list_student_enrolments(self, student_id: int) -> list[ReportEnrolmentRow]:
        """Return all enrolments for one student, including historical rows."""
        return self._list_enrolments(
            where_clause="e.student_id = ?",
            parameters=(student_id,),
            order_by="lower(c.course_code), e.enrolment_date, e.enrolment_id",
        )

    def list_course_enrolments(self, course_id: int) -> list[ReportEnrolmentRow]:
        """Return all enrolments for one course, including historical rows."""
        return self._list_enrolments(
            where_clause="e.course_id = ?",
            parameters=(course_id,),
            order_by=(
                "lower(s.last_name), lower(s.first_name), "
                "lower(s.student_number), e.enrolment_date, e.enrolment_id"
            ),
        )

    def list_active_students_for_course(self, course_id: int) -> list[ReportStudent]:
        """Return students with active enrolments in one course."""
        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    """
                    SELECT DISTINCT
                        s.student_id,
                        s.student_number,
                        s.first_name,
                        s.last_name,
                        s.status
                    FROM course_enrolments e
                    JOIN students s ON s.student_id = e.student_id
                    WHERE e.course_id = ?
                      AND e.status = ?
                    ORDER BY lower(s.last_name), lower(s.first_name),
                             lower(s.student_number), s.student_id
                    """,
                    (course_id, ENROLMENT_ACTIVE_STATUS),
                ).fetchall()

            return [_student_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Report course students could not be listed.") from error

    def list_trainer_assignments_for_course(
        self,
        course_id: int,
    ) -> list[ReportTrainerAssignmentRow]:
        """Return all trainer assignments for one course."""
        return self._list_trainer_assignments(
            where_clause="a.course_id = ?",
            parameters=(course_id,),
            order_by=(
                "lower(t.last_name), lower(t.first_name), "
                "lower(t.trainer_number), a.assigned_from, a.assignment_id"
            ),
        )

    def list_trainer_assignments_for_trainer(
        self,
        trainer_id: int,
    ) -> list[ReportTrainerAssignmentRow]:
        """Return all course assignments for one trainer."""
        return self._list_trainer_assignments(
            where_clause="a.trainer_id = ?",
            parameters=(trainer_id,),
            order_by="lower(c.course_code), a.assigned_from, a.assignment_id",
        )

    def list_attendance_records_for_student(
        self,
        student_id: int,
        course_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[ReportAttendanceRecordSource]:
        """Return attendance status rows for one student."""
        where_parts = ["r.student_id = ?"]
        parameters: list[int | str] = [student_id]
        if course_id is not None:
            where_parts.append("session.course_id = ?")
            parameters.append(course_id)
        if date_from is not None:
            where_parts.append("session.session_date >= ?")
            parameters.append(date_from)
        if date_to is not None:
            where_parts.append("session.session_date <= ?")
            parameters.append(date_to)

        return self._list_attendance_records(where_parts, parameters)

    def list_attendance_records_for_course(
        self,
        course_id: int,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[ReportAttendanceRecordSource]:
        """Return attendance status rows for one course."""
        where_parts = ["session.course_id = ?"]
        parameters: list[int | str] = [course_id]
        if date_from is not None:
            where_parts.append("session.session_date >= ?")
            parameters.append(date_from)
        if date_to is not None:
            where_parts.append("session.session_date <= ?")
            parameters.append(date_to)

        return self._list_attendance_records(where_parts, parameters)

    def list_attendance_sessions_for_course(
        self,
        course_id: int,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[ReportAttendanceSessionSource]:
        """Return per-session attendance counts for one course."""
        where_parts = ["s.course_id = ?"]
        where_parameters: list[int | str] = [course_id]
        if date_from is not None:
            where_parts.append("s.session_date >= ?")
            where_parameters.append(date_from)
        if date_to is not None:
            where_parts.append("s.session_date <= ?")
            where_parameters.append(date_to)

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        s.session_id,
                        s.course_id,
                        s.session_date,
                        s.topic,
                        COUNT(r.attendance_record_id) AS record_count,
                        SUM(CASE WHEN r.status = ? THEN 1 ELSE 0 END) AS present_count,
                        SUM(CASE WHEN r.status = ? THEN 1 ELSE 0 END) AS late_count,
                        SUM(CASE WHEN r.status = ? THEN 1 ELSE 0 END) AS absent_count,
                        SUM(CASE WHEN r.status = ? THEN 1 ELSE 0 END) AS excused_count,
                        SUM(CASE WHEN r.status = ? THEN 1 ELSE 0 END) AS unknown_count
                    FROM attendance_sessions s
                    LEFT JOIN attendance_records r ON r.session_id = s.session_id
                    WHERE {" AND ".join(where_parts)}
                    GROUP BY s.session_id, s.course_id, s.session_date, s.topic
                    ORDER BY s.session_date, lower(s.topic), s.session_id
                    """,
                    (
                        ATTENDANCE_PRESENT_STATUS,
                        ATTENDANCE_LATE_STATUS,
                        ATTENDANCE_ABSENT_STATUS,
                        ATTENDANCE_EXCUSED_STATUS,
                        ATTENDANCE_UNKNOWN_STATUS,
                        *where_parameters,
                    ),
                ).fetchall()

            return [_attendance_session_source_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError(
                "Report attendance sessions could not be listed."
            ) from error

    def list_assessments_for_course(self, course_id: int) -> list[ReportAssessment]:
        """Return all assessments for one course, including archived rows."""
        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        a.assessment_id,
                        a.course_id,
                        c.course_code,
                        c.course_name,
                        c.status AS course_status,
                        a.module_id,
                        module.module_code,
                        module.module_name,
                        module.status AS module_status,
                        a.assessment_name,
                        a.assessment_type,
                        a.max_mark,
                        a.weight,
                        a.pass_mark,
                        a.status
                    FROM assessments a
                    JOIN courses c ON c.course_id = a.course_id
                    LEFT JOIN modules module ON module.module_id = a.module_id
                    WHERE a.course_id = ?
                    ORDER BY {_assessment_order_by()}
                    """,
                    (course_id,),
                ).fetchall()

            return [_assessment_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Report assessments could not be listed.") from error

    def list_student_assessment_sources(
        self,
        student_id: int,
    ) -> list[StudentAssessmentSource]:
        """Return assessments from the student's enrolled courses with marks."""
        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        a.assessment_id,
                        a.course_id,
                        c.course_code,
                        c.course_name,
                        c.status AS course_status,
                        a.module_id,
                        module.module_code,
                        module.module_name,
                        module.status AS module_status,
                        a.assessment_name,
                        a.assessment_type,
                        a.max_mark,
                        a.weight,
                        a.pass_mark,
                        a.status,
                        mark.mark_id,
                        mark.mark_obtained,
                        mark.captured_at,
                        mark.notes
                    FROM assessments a
                    JOIN courses c ON c.course_id = a.course_id
                    LEFT JOIN modules module ON module.module_id = a.module_id
                    JOIN marks mark
                        ON mark.assessment_id = a.assessment_id
                       AND mark.student_id = ?
                    WHERE EXISTS (
                        SELECT 1
                        FROM course_enrolments e
                        WHERE e.student_id = ?
                          AND e.course_id = a.course_id
                    )
                    ORDER BY {_assessment_order_by()}
                    """,
                    (student_id, student_id),
                ).fetchall()

            return [_student_assessment_source_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError(
                "Report student assessments could not be listed."
            ) from error

    def list_marks_for_assessment(
        self,
        assessment_id: int,
    ) -> list[ReportMarkSource]:
        """Return all recorded marks for one assessment."""
        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    """
                    SELECT
                        s.student_id,
                        s.student_number,
                        s.first_name,
                        s.last_name,
                        s.status,
                        mark.mark_id,
                        mark.assessment_id,
                        mark.mark_obtained,
                        mark.captured_at,
                        mark.notes
                    FROM marks mark
                    JOIN students s ON s.student_id = mark.student_id
                    WHERE mark.assessment_id = ?
                    ORDER BY lower(s.last_name), lower(s.first_name),
                             lower(s.student_number), mark.mark_id
                    """,
                    (assessment_id,),
                ).fetchall()

            return [_mark_source_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Report marks could not be listed.") from error

    def _list_enrolments(
        self,
        where_clause: str,
        parameters: tuple[int, ...],
        order_by: str,
    ) -> list[ReportEnrolmentRow]:
        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        e.enrolment_id,
                        e.student_id,
                        s.student_number,
                        s.first_name AS student_first_name,
                        s.last_name AS student_last_name,
                        s.first_name || ' ' || s.last_name AS student_name,
                        s.status AS student_status,
                        e.course_id,
                        c.course_code,
                        c.course_name,
                        c.status AS course_status,
                        e.enrolment_date,
                        e.status,
                        e.cancelled_at,
                        e.cancellation_reason
                    FROM course_enrolments e
                    JOIN students s ON s.student_id = e.student_id
                    JOIN courses c ON c.course_id = e.course_id
                    WHERE {where_clause}
                    ORDER BY {order_by}
                    """,
                    parameters,
                ).fetchall()

            return [_enrolment_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Report enrolments could not be listed.") from error

    def _list_trainer_assignments(
        self,
        where_clause: str,
        parameters: tuple[int, ...],
        order_by: str,
    ) -> list[ReportTrainerAssignmentRow]:
        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        a.assignment_id,
                        a.trainer_id,
                        t.trainer_number,
                        t.first_name || ' ' || t.last_name AS trainer_name,
                        t.status AS trainer_status,
                        a.course_id,
                        c.course_code,
                        c.course_name,
                        c.status AS course_status,
                        a.assigned_from,
                        a.assigned_to,
                        a.status
                    FROM trainer_assignments a
                    JOIN trainers t ON t.trainer_id = a.trainer_id
                    JOIN courses c ON c.course_id = a.course_id
                    WHERE {where_clause}
                    ORDER BY {order_by}
                    """,
                    parameters,
                ).fetchall()

            return [_trainer_assignment_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError(
                "Report trainer assignments could not be listed."
            ) from error

    def _list_attendance_records(
        self,
        where_parts: list[str],
        parameters: list[int | str],
    ) -> list[ReportAttendanceRecordSource]:
        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        r.session_id,
                        session.course_id,
                        r.student_id,
                        r.status
                    FROM attendance_records r
                    JOIN attendance_sessions session
                        ON session.session_id = r.session_id
                    JOIN courses c ON c.course_id = session.course_id
                    JOIN students s ON s.student_id = r.student_id
                    WHERE {" AND ".join(where_parts)}
                    ORDER BY session.session_date, lower(c.course_code),
                             lower(session.topic), session.session_id,
                             lower(s.last_name), lower(s.first_name),
                             lower(s.student_number), r.attendance_record_id
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_attendance_record_source_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError(
                "Report attendance records could not be listed."
            ) from error


def _count_all(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS row_count FROM {table_name}").fetchone()
    return row["row_count"]


def _count_status(connection: sqlite3.Connection, table_name: str, status: str) -> int:
    if table_name in {"students", "trainers"} and status == ACTIVE_STATUS:
        row = connection.execute(
            f"SELECT COUNT(*) AS row_count FROM {table_name} WHERE status IN (?, ?)",
            (ACTIVE_STATUS, INACTIVE_STATUS),
        ).fetchone()
        return row["row_count"]

    row = connection.execute(
        f"SELECT COUNT(*) AS row_count FROM {table_name} WHERE status = ?",
        (status,),
    ).fetchone()
    return row["row_count"]


def _student_from_row(row) -> ReportStudent:
    return ReportStudent(
        student_id=row["student_id"],
        student_number=row["student_number"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        status=row["status"],
    )


def _course_from_row(row) -> ReportCourse:
    return ReportCourse(
        course_id=row["course_id"],
        course_code=row["course_code"],
        course_name=row["course_name"],
        status=row["status"],
    )


def _trainer_from_row(row) -> ReportTrainer:
    return ReportTrainer(
        trainer_id=row["trainer_id"],
        trainer_number=row["trainer_number"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        status=row["status"],
    )


def _module_from_row(row) -> ReportModule:
    return ReportModule(
        module_id=row["module_id"],
        course_id=row["course_id"],
        module_code=row["module_code"],
        module_name=row["module_name"],
        sequence_number=row["sequence_number"],
        status=row["status"],
    )


def _enrolment_from_row(row) -> ReportEnrolmentRow:
    return ReportEnrolmentRow(
        enrolment_id=row["enrolment_id"],
        student_id=row["student_id"],
        student_number=row["student_number"],
        student_first_name=row["student_first_name"],
        student_last_name=row["student_last_name"],
        student_name=row["student_name"],
        student_status=row["student_status"],
        course_id=row["course_id"],
        course_code=row["course_code"],
        course_name=row["course_name"],
        course_status=row["course_status"],
        enrolment_date=row["enrolment_date"],
        status=row["status"],
        cancelled_at=row["cancelled_at"],
        cancellation_reason=row["cancellation_reason"],
    )


def _trainer_assignment_from_row(row) -> ReportTrainerAssignmentRow:
    return ReportTrainerAssignmentRow(
        assignment_id=row["assignment_id"],
        trainer_id=row["trainer_id"],
        trainer_number=row["trainer_number"],
        trainer_name=row["trainer_name"],
        trainer_status=row["trainer_status"],
        course_id=row["course_id"],
        course_code=row["course_code"],
        course_name=row["course_name"],
        course_status=row["course_status"],
        assigned_from=row["assigned_from"],
        assigned_to=row["assigned_to"],
        status=row["status"],
    )


def _assessment_from_row(row) -> ReportAssessment:
    return ReportAssessment(
        assessment_id=row["assessment_id"],
        course_id=row["course_id"],
        course_code=row["course_code"],
        course_name=row["course_name"],
        course_status=row["course_status"],
        module_id=row["module_id"],
        module_code=row["module_code"],
        module_name=row["module_name"],
        module_status=row["module_status"],
        assessment_name=row["assessment_name"],
        assessment_type=row["assessment_type"],
        max_mark=decimal_from_storage(row["max_mark"]),
        weight=_optional_decimal_from_storage(row["weight"]),
        pass_mark=_optional_decimal_from_storage(row["pass_mark"]),
        status=row["status"],
    )


def _attendance_record_source_from_row(row) -> ReportAttendanceRecordSource:
    return ReportAttendanceRecordSource(
        session_id=row["session_id"],
        course_id=row["course_id"],
        student_id=row["student_id"],
        status=row["status"],
    )


def _attendance_session_source_from_row(row) -> ReportAttendanceSessionSource:
    return ReportAttendanceSessionSource(
        session_id=row["session_id"],
        course_id=row["course_id"],
        session_date=row["session_date"],
        topic=row["topic"],
        record_count=row["record_count"],
        present_count=row["present_count"] or 0,
        late_count=row["late_count"] or 0,
        absent_count=row["absent_count"] or 0,
        excused_count=row["excused_count"] or 0,
        unknown_count=row["unknown_count"] or 0,
    )


def _student_assessment_source_from_row(row) -> StudentAssessmentSource:
    return StudentAssessmentSource(
        assessment=_assessment_from_row(row),
        mark_id=row["mark_id"],
        mark_obtained=_optional_decimal_from_storage(row["mark_obtained"]),
        captured_at=row["captured_at"],
        notes=row["notes"],
    )


def _mark_source_from_row(row) -> ReportMarkSource:
    student = ReportStudent(
        student_id=row["student_id"],
        student_number=row["student_number"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        status=row["status"],
    )
    return ReportMarkSource(
        student=student,
        mark_id=row["mark_id"],
        assessment_id=row["assessment_id"],
        mark_obtained=decimal_from_storage(row["mark_score"]),
        captured_at=row["captured_at"],
        notes=row["notes"],
    )


def _optional_decimal_from_storage(value: str | None):
    if value is None:
        return None

    return decimal_from_storage(value)


def _assessment_order_by() -> str:
    return (
        "lower(c.course_code), "
        "CASE WHEN a.module_id IS NULL THEN 0 ELSE 1 END, "
        "COALESCE(module.sequence_number, 0), "
        "lower(COALESCE(module.module_code, '')), "
        "lower(a.assessment_name), "
        "CAST(a.assessment_id AS TEXT)"
    )
