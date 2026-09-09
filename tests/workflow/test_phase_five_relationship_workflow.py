"""End-to-end Phase 5 workflow tests."""

import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.course import COURSE_ACTIVE_STATUS
from itca_training_centre.models.course_enrolment import ENROLMENT_CANCELLED_STATUS
from itca_training_centre.models.trainer_assignment import ASSIGNMENT_ACTIVE_STATUS
from itca_training_centre.services.course_enrolment_service import CourseEnrolmentService
from itca_training_centre.services.course_service import CourseService
from itca_training_centre.services.module_service import ModuleService
from itca_training_centre.services.student_service import StudentService
from itca_training_centre.services.trainer_assignment_service import TrainerAssignmentService
from itca_training_centre.services.trainer_service import TrainerService
from itca_training_centre.utils.exceptions import DuplicateRecordError, ValidationError
from tests.helpers import temporary_database_path


class PhaseFiveRelationshipWorkflowTests(unittest.TestCase):
    def test_enrolment_and_trainer_assignment_workflow_preserves_history(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)
            student_service = StudentService(database_path)
            course_service = CourseService(database_path)
            module_service = ModuleService(database_path)
            trainer_service = TrainerService(database_path)
            enrolment_service = CourseEnrolmentService(database_path)
            assignment_service = TrainerAssignmentService(database_path)

            student_a = student_service.register_student("STU-1001", "Amina", "Nkosi")
            student_b = student_service.register_student("STU-1002", "Bongi", "Mokoena")
            course_a = course_service.create_course(
                "PYF101",
                "Python Fundamentals",
                fee_amount="1500",
                status=COURSE_ACTIVE_STATUS,
            )
            course_b = course_service.create_course(
                "SQL101",
                "SQLite Basics",
                fee_amount="1200",
                status=COURSE_ACTIVE_STATUS,
            )
            module = module_service.create_module("PYF101", "MOD-101", "Variables", 1)
            trainer_a = trainer_service.register_trainer("TRN-1001", "Thandi", "Dlamini")
            trainer_b = trainer_service.register_trainer("TRN-1002", "Ayesha", "Banda")

            enrolment_a = enrolment_service.enrol_student(
                "STU-1001",
                "PYF101",
                "2026-09-01",
            )
            enrolment_b = enrolment_service.enrol_student(
                "STU-1002",
                "PYF101",
                "2026-09-02",
            )
            enrolment_c = enrolment_service.enrol_student(
                "STU-1001",
                "SQL101",
                "2026-09-03",
            )
            with self.assertRaisesRegex(DuplicateRecordError, "actively enrolled"):
                enrolment_service.enrol_student("STU-1001", "PYF101", "2026-09-04")

            cancelled = enrolment_service.cancel_enrolment(
                "STU-1002",
                "PYF101",
                "2026-09-15",
                "Moved to a later group",
            )
            replacement = enrolment_service.enrol_student(
                "STU-1002",
                "PYF101",
                "2026-10-01",
            )

            assignment_a = assignment_service.assign_trainer(
                "TRN-1001",
                "PYF101",
                "2026-09-01",
            )
            assignment_b = assignment_service.assign_trainer(
                "TRN-1002",
                "SQL101",
                "2026-09-01",
            )
            assignment_c = assignment_service.assign_trainer(
                "TRN-1001",
                "SQL101",
                "2026-09-05",
            )
            with self.assertRaisesRegex(DuplicateRecordError, "actively assigned"):
                assignment_service.assign_trainer("TRN-1001", "PYF101", "2026-09-10")

            ended = assignment_service.end_assignment(
                "TRN-1001",
                "PYF101",
                "2026-09-30",
            )
            reactivated = assignment_service.reactivate_assignment("TRN-1001", "PYF101")

            student_service.deactivate_student("STU-1001")
            course_service.deactivate_course("SQL101")
            module_service.deactivate_module("PYF101", "MOD-101")
            trainer_service.deactivate_trainer("TRN-1002")

            with self.assertRaisesRegex(ValidationError, "Student must be active"):
                enrolment_service.enrol_student("STU-1001", "PYF101", "2026-11-01")
            with self.assertRaisesRegex(ValidationError, "Course must be active"):
                enrolment_service.enrol_student("STU-1002", "SQL101", "2026-11-01")
            with self.assertRaisesRegex(ValidationError, "Trainer must be active"):
                assignment_service.assign_trainer("TRN-1002", "PYF101", "2026-11-01")
            with self.assertRaisesRegex(ValidationError, "Course must be active"):
                assignment_service.assign_trainer("TRN-1001", "SQL101", "2026-11-01")

            with open_database(database_path) as connection:
                student_count = connection.execute("SELECT COUNT(*) FROM students").fetchone()[0]
                course_count = connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
                module_count = connection.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
                trainer_count = connection.execute("SELECT COUNT(*) FROM trainers").fetchone()[0]
                enrolment_count = connection.execute(
                    "SELECT COUNT(*) FROM course_enrolments"
                ).fetchone()[0]
                assignment_count = connection.execute(
                    "SELECT COUNT(*) FROM trainer_assignments"
                ).fetchone()[0]

        self.assertEqual(student_a.student_id, enrolment_a.student_id)
        self.assertEqual(student_b.student_id, cancelled.student_id)
        self.assertEqual(course_a.course_id, replacement.course_id)
        self.assertEqual(course_b.course_id, enrolment_c.course_id)
        self.assertEqual(ENROLMENT_CANCELLED_STATUS, cancelled.status)
        self.assertNotEqual(enrolment_b.enrolment_id, replacement.enrolment_id)
        self.assertEqual(trainer_a.trainer_id, assignment_a.trainer_id)
        self.assertEqual(trainer_b.trainer_id, assignment_b.trainer_id)
        self.assertEqual(course_b.course_id, assignment_c.course_id)
        self.assertEqual(assignment_a.assignment_id, ended.assignment_id)
        self.assertEqual(assignment_a.assignment_id, reactivated.assignment_id)
        self.assertEqual(ASSIGNMENT_ACTIVE_STATUS, reactivated.status)
        self.assertEqual(course_a.course_id, module.course_id)
        self.assertEqual(2, student_count)
        self.assertEqual(2, course_count)
        self.assertEqual(1, module_count)
        self.assertEqual(2, trainer_count)
        self.assertEqual(4, enrolment_count)
        self.assertEqual(3, assignment_count)


if __name__ == "__main__":
    unittest.main()
