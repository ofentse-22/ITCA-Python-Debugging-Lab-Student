"""Integration tests for attendance service business behavior."""

import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.attendance_record import (
    ATTENDANCE_ABSENT_STATUS,
    ATTENDANCE_EXCUSED_STATUS,
    ATTENDANCE_LATE_STATUS,
    ATTENDANCE_PRESENT_STATUS,
    ATTENDANCE_UNKNOWN_STATUS,
    AttendanceRegisterEntry,
)
from itca_training_centre.models.course import (
    COURSE_ACTIVE_STATUS,
    COURSE_PLANNED_STATUS,
)
from itca_training_centre.services.attendance_service import AttendanceService
from itca_training_centre.services.course_enrolment_service import CourseEnrolmentService
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.module_service import ModuleService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.services.trainer_assignment_service import TrainerAssignmentService
from itca_training_centre.services.trainer_service import TrainerService
from itca_training_centre.utils.exceptions import (
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from tests.helpers import temporary_database_path


class AttendanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_database_path()
        self.database_path = self.database_context.__enter__()
        initialize_database(self.database_path)
        self.student_service = StudentService(self.database_path)
        self.course_service = CourseService(self.database_path)
        self.module_service = ModuleService(self.database_path)
        self.enrolment_service = CourseEnrolmentService(self.database_path)
        self.trainer_service = TrainerService(self.database_path)
        self.assignment_service = TrainerAssignmentService(self.database_path)
        self.service = AttendanceService(self.database_path)

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def _create_student(
        self,
        student_number="STU-1001",
        first_name="Amina",
        last_name="Nkosi",
    ):
        return self.student_service.register_student(
            student_number,
            first_name,
            last_name,
        )

    def _create_course(self, course_code="PYF101", status=COURSE_ACTIVE_STATUS):
        return self.course_service.create_course(
            course_code,
            f"{course_code} Course",
            fee_amount="0",
            status=status,
        )

    def _enrol(self, student_number="STU-1001", course_code="PYF101", date="2026-09-01"):
        return self.enrolment_service.enrol_student(student_number, course_code, date)

    def test_create_session_requires_existing_active_course(self):
        self._create_course()

        session = self.service.create_session(
            course_code=" pyf101 ",
            session_date="2026-09-02",
            topic="  Control   Flow  ",
        )

        self.assertEqual("2026-09-02", session.session_date)
        self.assertEqual("Control Flow", session.topic)

        with self.assertRaisesRegex(RecordNotFoundError, "No course"):
            self.service.create_session("MISSING", "2026-09-02", "Control Flow")

        self._create_course("SQL101", status=COURSE_PLANNED_STATUS)
        with self.assertRaisesRegex(ValidationError, "Course must be active"):
            self.service.create_session("SQL101", "2026-09-02", "Tables")

    def test_duplicate_session_and_invalid_dates_are_rejected(self):
        self._create_course()
        self.service.create_session("PYF101", "2026-09-02", "Control Flow")

        with self.assertRaisesRegex(DuplicateRecordError, "already exists"):
            self.service.create_session("PYF101", "2026-09-02", "Control Flow")
        with self.assertRaisesRegex(ValidationError, "Session date"):
            self.service.create_session("PYF101", "09/02/2026", "Control Flow")
        with self.assertRaisesRegex(ValidationError, "Date from"):
            self.service.list_sessions(date_from="09/01/2026")
        with self.assertRaisesRegex(ValidationError, "Date from may not"):
            self.service.list_sessions(date_from="2026-09-03", date_to="2026-09-01")

    def test_list_sessions_filters_by_course_date_and_topic(self):
        self._create_course("PYF101")
        self._create_course("SQL101")
        first = self.service.create_session("PYF101", "2026-09-01", "Control Flow")
        second = self.service.create_session("PYF101", "2026-09-02", "Loops")
        third = self.service.create_session("SQL101", "2026-09-02", "Tables")

        self.assertEqual(
            [first.session_id, second.session_id, third.session_id],
            [session.session_id for session in self.service.list_sessions()],
        )
        self.assertEqual(
            [second.session_id],
            [
                session.session_id
                for session in self.service.list_sessions(
                    course_code="PYF101",
                    date_from="2026-09-02",
                    topic_search="loop",
                )
            ],
        )

    def test_eligible_students_require_active_enrolment_before_session_date(self):
        self._create_course()
        self._create_student("STU-1001", "Amina", "Nkosi")
        self._create_student("STU-1002", "Bongi", "Mokoena")
        self._create_student("STU-1003", "Celia", "Zulu")
        self._enrol("STU-1001", "PYF101", "2026-09-01")
        self._enrol("STU-1002", "PYF101", "2026-09-10")
        session = self.service.create_session("PYF101", "2026-09-02", "Control Flow")

        eligible = self.service.list_eligible_students(session.session_id)

        self.assertEqual(["STU-1001"], [student.student_number for student in eligible])

    def test_record_attendance_requires_eligible_student(self):
        self._create_course()
        self._create_student("STU-1001", "Amina", "Nkosi")
        self._create_student("STU-1002", "Bongi", "Mokoena")
        self._create_student("STU-1003", "Celia", "Zulu")
        self._enrol("STU-1001", "PYF101", "2026-09-01")
        self._enrol("STU-1002", "PYF101", "2026-09-01")
        self.enrolment_service.cancel_enrolment(
            "STU-1002",
            "PYF101",
            "2026-09-05",
            "Student withdrew",
        )
        session = self.service.create_session("PYF101", "2026-09-02", "Control Flow")

        record = self.service.record_attendance(
            session.session_id,
            "STU-1001",
            ATTENDANCE_PRESENT_STATUS,
            "On time",
        )

        self.assertEqual(ATTENDANCE_PRESENT_STATUS, record.status)
        self.assertEqual("On time", record.notes)
        with self.assertRaisesRegex(RecordNotFoundError, "No student"):
            self.service.record_attendance(
                session.session_id,
                "STU-9999",
                ATTENDANCE_PRESENT_STATUS,
            )
        with self.assertRaisesRegex(RecordNotFoundError, "No attendance session"):
            self.service.record_attendance(999, "STU-1001", ATTENDANCE_PRESENT_STATUS)
        with self.assertRaisesRegex(ValidationError, "not eligible"):
            self.service.record_attendance(
                session.session_id,
                "STU-1002",
                ATTENDANCE_PRESENT_STATUS,
            )
        with self.assertRaisesRegex(ValidationError, "not eligible"):
            self.service.record_attendance(
                session.session_id,
                "STU-1003",
                ATTENDANCE_PRESENT_STATUS,
            )
        with self.assertRaisesRegex(ValidationError, "Attendance status"):
            self.service.record_attendance(session.session_id, "STU-1001", "maybe")

    def test_duplicate_record_is_rejected_and_update_keeps_same_id(self):
        self._create_course()
        self._create_student()
        self._enrol()
        session = self.service.create_session("PYF101", "2026-09-02", "Control Flow")
        created = self.service.record_attendance(
            session.session_id,
            "STU-1001",
            ATTENDANCE_ABSENT_STATUS,
            "Sick",
        )

        with self.assertRaisesRegex(DuplicateRecordError, "already recorded"):
            self.service.record_attendance(
                session.session_id,
                "STU-1001",
                ATTENDANCE_PRESENT_STATUS,
            )

        self.enrolment_service.cancel_enrolment(
            "STU-1001",
            "PYF101",
            "2026-09-05",
            "Student withdrew",
        )
        updated = self.service.update_attendance(
            session.session_id,
            "STU-1001",
            ATTENDANCE_LATE_STATUS,
            "Corrected after sign-in review",
        )

        self.assertEqual(created.attendance_record_id, updated.attendance_record_id)
        self.assertEqual(ATTENDANCE_LATE_STATUS, updated.status)
        self.assertEqual("Corrected after sign-in review", updated.notes)

    def test_class_register_validates_before_persisting_and_rejects_duplicates(self):
        self._create_course()
        self._create_student("STU-1001", "Amina", "Nkosi")
        self._create_student("STU-1002", "Bongi", "Mokoena")
        self._enrol("STU-1001")
        self._enrol("STU-1002")
        session = self.service.create_session("PYF101", "2026-09-02", "Control Flow")

        with self.assertRaisesRegex(ValidationError, "Attendance status"):
            self.service.record_class_attendance(
                session.session_id,
                [
                    AttendanceRegisterEntry("STU-1001", ATTENDANCE_PRESENT_STATUS),
                    AttendanceRegisterEntry("STU-1002", "maybe"),
                ],
            )
        self.assertEqual([], self.service.list_session_attendance(session.session_id))

        records = self.service.record_class_attendance(
            session.session_id,
            [
                AttendanceRegisterEntry("STU-1001", ATTENDANCE_PRESENT_STATUS),
                AttendanceRegisterEntry("STU-1002", ATTENDANCE_ABSENT_STATUS, "Absent"),
            ],
        )

        self.assertEqual(2, len(records))
        with self.assertRaisesRegex(DuplicateRecordError, "already recorded"):
            self.service.record_class_attendance(
                session.session_id,
                [AttendanceRegisterEntry("STU-1001", ATTENDANCE_PRESENT_STATUS)],
            )

        second_session = self.service.create_session("PYF101", "2026-09-03", "Loops")
        with self.assertRaisesRegex(DuplicateRecordError, "more than once"):
            self.service.record_class_attendance(
                second_session.session_id,
                [
                    AttendanceRegisterEntry("STU-1001", ATTENDANCE_PRESENT_STATUS),
                    AttendanceRegisterEntry("stu-1001", ATTENDANCE_ABSENT_STATUS),
                ],
            )

    def test_attendance_summary_handles_no_records_mixed_statuses_and_zero_denominator(self):
        self._create_course()
        self._create_student()
        self._enrol()

        empty_summary = self.service.calculate_student_attendance("STU-1001", "PYF101")
        self.assertEqual(0, empty_summary.total_records)
        self.assertIsNone(empty_summary.attendance_percentage)

        statuses = [
            ATTENDANCE_PRESENT_STATUS,
            ATTENDANCE_ABSENT_STATUS,
            ATTENDANCE_LATE_STATUS,
            ATTENDANCE_EXCUSED_STATUS,
            ATTENDANCE_UNKNOWN_STATUS,
        ]
        for index, status in enumerate(statuses, start=1):
            session = self.service.create_session(
                "PYF101",
                f"2026-09-{index:02d}",
                f"Topic {index}",
            )
            self.service.record_attendance(session.session_id, "STU-1001", status)

        summary = self.service.calculate_student_attendance("STU-1001", "PYF101")

        self.assertEqual(5, summary.total_records)
        self.assertEqual(1, summary.present_count)
        self.assertEqual(1, summary.late_count)
        self.assertEqual(1, summary.absent_count)
        self.assertEqual(1, summary.excused_count)
        self.assertEqual(1, summary.unknown_count)
        self.assertEqual(3, summary.percentage_denominator)
        self.assertEqual(66.67, summary.attendance_percentage)

        second_student = self._create_student("STU-1002", "Bongi", "Mokoena")
        self._enrol("STU-1002")
        excused_only_session = self.service.create_session(
            "PYF101",
            "2026-09-20",
            "Workshop",
        )
        self.service.record_attendance(
            excused_only_session.session_id,
            second_student.student_number,
            ATTENDANCE_EXCUSED_STATUS,
        )

        excused_summary = self.service.calculate_student_attendance("STU-1002", "PYF101")
        self.assertEqual(1, excused_summary.total_records)
        self.assertEqual(0, excused_summary.percentage_denominator)
        self.assertIsNone(excused_summary.attendance_percentage)

    def test_low_attendance_uses_threshold_and_skips_students_without_percentage(self):
        self._create_course()
        self._create_student("STU-1001", "Amina", "Nkosi")
        self._create_student("STU-1002", "Bongi", "Mokoena")
        self._create_student("STU-1003", "Celia", "Zulu")
        self._enrol("STU-1001")
        self._enrol("STU-1002")
        self._enrol("STU-1003")
        session_a = self.service.create_session("PYF101", "2026-09-01", "Control Flow")
        session_b = self.service.create_session("PYF101", "2026-09-02", "Loops")
        self.service.record_attendance(session_a.session_id, "STU-1001", ATTENDANCE_PRESENT_STATUS)
        self.service.record_attendance(session_b.session_id, "STU-1001", ATTENDANCE_ABSENT_STATUS)
        self.service.record_attendance(session_a.session_id, "STU-1002", ATTENDANCE_PRESENT_STATUS)

        low_students = self.service.list_low_attendance_students("PYF101", "80")

        self.assertEqual(1, len(low_students))
        self.assertEqual(
            self.student_service.get_student_by_number("STU-1001").student_id,
            low_students[0].student_id,
        )
        self.assertEqual(50.0, low_students[0].attendance_percentage)
        with self.assertRaisesRegex(ValidationError, "threshold"):
            self.service.list_low_attendance_students("PYF101", "101")
        for threshold in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(threshold=threshold):
                with self.assertRaisesRegex(ValidationError, "finite number"):
                    self.service.list_low_attendance_students("PYF101", threshold)

    def test_historical_attendance_survives_parent_status_changes(self):
        student = self._create_student()
        course = self._create_course()
        module = self.module_service.create_module("PYF101", "MOD-101", "Variables", 1)
        trainer = self.trainer_service.register_trainer("TRN-1001", "Thandi", "Dlamini")
        self.assignment_service.assign_trainer("TRN-1001", "PYF101", "2026-09-01")
        self._enrol()
        session = self.service.create_session("PYF101", "2026-09-02", "Control Flow")
        record = self.service.record_attendance(
            session.session_id,
            "STU-1001",
            ATTENDANCE_PRESENT_STATUS,
        )

        self.enrolment_service.cancel_enrolment(
            "STU-1001",
            "PYF101",
            "2026-09-05",
            "Student withdrew",
        )
        self.student_service.deactivate_student("STU-1001")
        self.module_service.deactivate_module("PYF101", "MOD-101")
        self.trainer_service.deactivate_trainer("TRN-1001")
        self.course_service.deactivate_course("PYF101")

        records = self.service.list_student_attendance("STU-1001", "PYF101")
        with open_database(self.database_path) as connection:
            record_count = connection.execute(
                "SELECT COUNT(*) FROM attendance_records"
            ).fetchone()[0]

        self.assertEqual(student.student_id, record.student_id)
        self.assertEqual(course.course_id, session.course_id)
        self.assertEqual(course.course_id, module.course_id)
        self.assertEqual(trainer.trainer_number, "TRN-1001")
        self.assertEqual([record.attendance_record_id], [item.attendance_record_id for item in records])
        self.assertEqual(1, record_count)


if __name__ == "__main__":
    unittest.main()
