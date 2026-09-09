"""End-to-end Phase 6 Attendance Management workflow tests."""

import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.attendance_record import (
    ATTENDANCE_ABSENT_STATUS,
    ATTENDANCE_EXCUSED_STATUS,
    ATTENDANCE_LATE_STATUS,
    ATTENDANCE_PRESENT_STATUS,
)
from itca_training_centre.models.course import COURSE_ACTIVE_STATUS
from itca_training_centre.services.attendance_service import AttendanceService
from itca_training_centre.services.course_enrolment_service import CourseEnrolmentService
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.module_service import ModuleService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.services.trainer_assignment_service import TrainerAssignmentService
from itca_training_centre.services.trainer_service import TrainerService
from itca_training_centre.utils.exceptions import DuplicateRecordError, ValidationError
from tests.helpers import temporary_database_path


class PhaseSixAttendanceWorkflowTests(unittest.TestCase):
    def test_attendance_workflow_preserves_history_and_calculates_percentages(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)
            student_service = StudentService(database_path)
            course_service = CourseService(database_path)
            module_service = ModuleService(database_path)
            trainer_service = TrainerService(database_path)
            assignment_service = TrainerAssignmentService(database_path)
            enrolment_service = CourseEnrolmentService(database_path)
            attendance_service = AttendanceService(database_path)

            student_a = student_service.register_student("STU-1001", "Amina", "Nkosi")
            student_b = student_service.register_student("STU-1002", "Bongi", "Mokoena")
            student_c = student_service.register_student("STU-1003", "Celia", "Zulu")
            course = course_service.create_course(
                "PYF101",
                "Python Fundamentals",
                fee_amount="1500",
                status=COURSE_ACTIVE_STATUS,
            )
            module = module_service.create_module("PYF101", "MOD-101", "Variables", 1)
            trainer = trainer_service.register_trainer("TRN-1001", "Thandi", "Dlamini")
            assignment = assignment_service.assign_trainer(
                "TRN-1001",
                "PYF101",
                "2026-09-01",
            )
            enrolment_service.enrol_student("STU-1001", "PYF101", "2026-09-01")
            enrolment_service.enrol_student("STU-1002", "PYF101", "2026-09-01")

            session_one = attendance_service.create_session(
                "PYF101",
                "2026-09-02",
                "Control Flow",
            )
            record_a_one = attendance_service.record_attendance(
                session_one.session_id,
                "STU-1001",
                ATTENDANCE_PRESENT_STATUS,
            )
            record_b_one = attendance_service.record_attendance(
                session_one.session_id,
                "STU-1002",
                ATTENDANCE_ABSENT_STATUS,
            )
            with self.assertRaisesRegex(ValidationError, "not eligible"):
                attendance_service.record_attendance(
                    session_one.session_id,
                    student_c.student_number,
                    ATTENDANCE_PRESENT_STATUS,
                )
            with self.assertRaisesRegex(DuplicateRecordError, "already recorded"):
                attendance_service.record_attendance(
                    session_one.session_id,
                    "STU-1001",
                    ATTENDANCE_PRESENT_STATUS,
                )

            corrected_b = attendance_service.update_attendance(
                session_one.session_id,
                "STU-1002",
                ATTENDANCE_LATE_STATUS,
                "Corrected after sign-in review",
            )
            session_two = attendance_service.create_session(
                "PYF101",
                "2026-09-03",
                "Loops",
            )
            record_a_two = attendance_service.record_attendance(
                session_two.session_id,
                "STU-1001",
                ATTENDANCE_ABSENT_STATUS,
                "Sick",
            )
            record_b_two = attendance_service.record_attendance(
                session_two.session_id,
                "STU-1002",
                ATTENDANCE_EXCUSED_STATUS,
                "Approved appointment",
            )

            student_a_summary = attendance_service.calculate_student_attendance(
                "STU-1001",
                "PYF101",
            )
            student_b_summary = attendance_service.calculate_student_attendance(
                "STU-1002",
                "PYF101",
            )
            low_attendance = attendance_service.list_low_attendance_students(
                "PYF101",
                "80",
            )
            session_one_register = attendance_service.list_session_attendance(
                session_one.session_id
            )
            student_a_history = attendance_service.list_student_attendance(
                "STU-1001",
                "PYF101",
            )

            enrolment_service.cancel_enrolment(
                "STU-1001",
                "PYF101",
                "2026-09-10",
                "Student withdrew",
            )
            student_service.deactivate_student("STU-1001")
            module_service.deactivate_module("PYF101", "MOD-101")
            trainer_service.deactivate_trainer("TRN-1001")
            course_service.deactivate_course("PYF101")

            records_after_status_changes = attendance_service.list_student_attendance(
                "STU-1001",
                "PYF101",
            )
            with open_database(database_path) as connection:
                session_count = connection.execute(
                    "SELECT COUNT(*) FROM attendance_sessions"
                ).fetchone()[0]
                record_count = connection.execute(
                    "SELECT COUNT(*) FROM attendance_records"
                ).fetchone()[0]

        self.assertEqual(student_a.student_id, record_a_one.student_id)
        self.assertEqual(student_b.student_id, record_b_one.student_id)
        self.assertEqual(course.course_id, session_one.course_id)
        self.assertEqual(course.course_id, module.course_id)
        self.assertEqual(trainer.trainer_id, assignment.trainer_id)
        self.assertEqual(record_b_one.attendance_record_id, corrected_b.attendance_record_id)
        self.assertEqual(ATTENDANCE_LATE_STATUS, corrected_b.status)
        self.assertEqual(2, student_a_summary.total_records)
        self.assertEqual(50.0, student_a_summary.attendance_percentage)
        self.assertEqual(2, student_b_summary.total_records)
        self.assertEqual(100.0, student_b_summary.attendance_percentage)
        self.assertEqual([student_a.student_id], [summary.student_id for summary in low_attendance])
        self.assertEqual(
            [record_b_one.attendance_record_id, record_a_one.attendance_record_id],
            [record.attendance_record_id for record in session_one_register],
        )
        self.assertEqual(
            [record_a_one.attendance_record_id, record_a_two.attendance_record_id],
            [record.attendance_record_id for record in student_a_history],
        )
        self.assertEqual(
            [record_a_one.attendance_record_id, record_a_two.attendance_record_id],
            [record.attendance_record_id for record in records_after_status_changes],
        )
        self.assertEqual(record_b_two.status, ATTENDANCE_EXCUSED_STATUS)
        self.assertEqual(2, session_count)
        self.assertEqual(4, record_count)


if __name__ == "__main__":
    unittest.main()
