"""Shared fictional data setup for reporting tests."""

from dataclasses import dataclass

from itca_training_centre.data.connection import open_database
from itca_training_centre.models.assessment import Assessment
from itca_training_centre.models.attendance_session import AttendanceSession
from itca_training_centre.models.course import Course
from itca_training_centre.models.module import Module
from itca_training_centre.models.student import Student
from itca_training_centre.models.trainer import Trainer
from itca_training_centre.services.assessment_service import AssessmentService
from itca_training_centre.services.attendance_service import AttendanceService
from itca_training_centre.services.course_enrolment_service import CourseEnrolmentService
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.module_service import ModuleService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.services.trainer_assignment_service import (
    TrainerAssignmentService,
)
from itca_training_centre.services.trainer_service import TrainerService


OPERATIONAL_TABLES = (
    "students",
    "courses",
    "modules",
    "trainers",
    "course_enrolments",
    "trainer_assignments",
    "attendance_sessions",
    "attendance_records",
    "assessments",
    "marks",
)


@dataclass(frozen=True)
class ReportingFixture:
    """Records created for report integration tests."""

    student_amina: Student
    student_bongi: Student
    student_celia: Student
    student_dineo: Student
    student_esi: Student
    student_no_enrolment: Student
    course_python: Course
    course_sql: Course
    module_variables: Module
    module_loops: Module
    trainer_thandi: Trainer
    trainer_omar: Trainer
    session_control_flow: AttendanceSession
    session_loops: AttendanceSession
    assessment_practical: Assessment
    assessment_quiz: Assessment
    assessment_sql: Assessment


def seed_reporting_data(database_path) -> ReportingFixture:
    """Create deterministic fictional data for Phase 8 report tests."""
    students = StudentService(database_path)
    courses = CourseService(database_path)
    modules = ModuleService(database_path)
    enrolments = CourseEnrolmentService(database_path)
    trainers = TrainerService(database_path)
    assignments = TrainerAssignmentService(database_path)
    attendance = AttendanceService(database_path)
    assessments = AssessmentService(database_path)

    student_amina = students.register_student("STU-1001", "Amina", "Nkosi")
    student_bongi = students.register_student("STU-1002", "Bongi", "Mokoena")
    student_celia = students.register_student("STU-1003", "Celia", "Zulu")
    student_dineo = students.register_student("STU-1004", "Dineo", "Abrahams")
    student_esi = students.register_student("STU-1005", "Esi", "Khumalo")
    student_no_enrolment = students.register_student("STU-9999", "No", "Enrolment")

    course_python = courses.create_course(
        "PYF101",
        "Python Fundamentals",
        fee_amount="1500",
        status="active",
    )
    course_sql = courses.create_course(
        "SQL101",
        "SQLite Basics",
        fee_amount="900",
        status="active",
    )

    module_variables = modules.create_module("PYF101", "MOD-101", "Variables", 1)
    module_loops = modules.create_module("PYF101", "MOD-102", "Loops", 2)
    modules.create_module("SQL101", "SQL-101", "Select Queries", 1)

    trainer_thandi = trainers.register_trainer("TRN-1001", "Thandi", "Dlamini")
    trainer_omar = trainers.register_trainer("TRN-1002", "Omar", "Patel")
    assignments.assign_trainer("TRN-1001", "PYF101", "2026-09-01")
    assignments.assign_trainer("TRN-1001", "SQL101", "2026-09-02")
    assignments.assign_trainer("TRN-1002", "PYF101", "2026-08-20")
    assignments.end_assignment("TRN-1002", "PYF101", "2026-09-05")

    for student_number in ("STU-1001", "STU-1002", "STU-1003", "STU-1005"):
        enrolments.enrol_student(student_number, "PYF101", "2026-09-01")
    enrolments.enrol_student("STU-1004", "SQL101", "2026-09-01")

    session_control_flow = attendance.create_session(
        "PYF101",
        "2026-09-02",
        "Control Flow",
    )
    attendance.record_attendance(session_control_flow.session_id, "STU-1001", "present")
    attendance.record_attendance(session_control_flow.session_id, "STU-1002", "absent")
    attendance.record_attendance(session_control_flow.session_id, "STU-1003", "unknown")
    attendance.record_attendance(session_control_flow.session_id, "STU-1005", "present")

    session_loops = attendance.create_session("PYF101", "2026-09-03", "Loops")
    attendance.record_attendance(session_loops.session_id, "STU-1001", "absent")
    attendance.record_attendance(session_loops.session_id, "STU-1002", "late")
    attendance.record_attendance(session_loops.session_id, "STU-1003", "excused")
    attendance.record_attendance(session_loops.session_id, "STU-1005", "absent")

    assessment_practical = assessments.create_assessment(
        "PYF101",
        "Variables Practical",
        "practical",
        "100",
        module_code="MOD-101",
        pass_mark="50",
    )
    assessments.record_mark(assessment_practical.assessment_id, "STU-1001", "0")
    assessments.record_mark(assessment_practical.assessment_id, "STU-1002", "75.5")
    assessments.record_mark(assessment_practical.assessment_id, "STU-1005", "40")

    assessment_quiz = assessments.create_assessment(
        "PYF101",
        "Course Quiz",
        "quiz",
        "3",
        pass_mark=None,
    )
    assessments.record_mark(assessment_quiz.assessment_id, "STU-1001", "1")

    assessment_sql = assessments.create_assessment(
        "SQL101",
        "Select Drill",
        "practical",
        "2.5",
        pass_mark="1.25",
    )
    assessments.record_mark(assessment_sql.assessment_id, "STU-1004", "1.25")

    enrolments.cancel_enrolment(
        "STU-1005",
        "PYF101",
        "2026-09-06",
        "Student moved cohort",
    )
    students.deactivate_student("STU-1005")
    modules.deactivate_module("PYF101", "MOD-101")
    assessments.deactivate_assessment(assessment_practical.assessment_id)

    return ReportingFixture(
        student_amina=student_amina,
        student_bongi=student_bongi,
        student_celia=student_celia,
        student_dineo=student_dineo,
        student_esi=student_esi,
        student_no_enrolment=student_no_enrolment,
        course_python=course_python,
        course_sql=course_sql,
        module_variables=module_variables,
        module_loops=module_loops,
        trainer_thandi=trainer_thandi,
        trainer_omar=trainer_omar,
        session_control_flow=session_control_flow,
        session_loops=session_loops,
        assessment_practical=assessment_practical,
        assessment_quiz=assessment_quiz,
        assessment_sql=assessment_sql,
    )


def operational_table_counts(database_path) -> dict[str, int]:
    """Return row counts for all operational tables."""
    with open_database(database_path) as connection:
        return {
            table_name: connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            for table_name in OPERATIONAL_TABLES
        }
