"""End-to-end Student Management workflow tests."""

import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.models.student import ACTIVE_STATUS, INACTIVE_STATUS
from itca_training_centre.services.student_service import StudentService
from tests.helpers import temporary_database_path


class StudentManagementWorkflowTests(unittest.TestCase):
    def test_register_update_search_deactivate_reactivate_workflow(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)
            service = StudentService(database_path)

            first = service.register_student(
                "STU-1001",
                "Amina",
                "Nkosi",
                "amina@example.edu",
                None,
            )
            service.register_student("STU-1002", "Bongi", "Mokoena")

            retrieved = service.get_student_by_number("STU-1001")
            updated = service.update_student(
                "STU-1001",
                "Amira",
                "Nkosi",
                "amira@example.edu",
                "555-0101",
            )
            search_results = service.search_students("Amira")
            inactive = service.deactivate_student("STU-1001")
            active_students = service.list_students()
            all_students = service.list_students(include_inactive=True)
            active_again = service.reactivate_student("STU-1001")

            with open_database(database_path) as connection:
                student_count = connection.execute(
                    "SELECT COUNT(*) FROM students"
                ).fetchone()[0]

        self.assertEqual(first.student_id, retrieved.student_id)
        self.assertEqual(first.student_id, updated.student_id)
        self.assertEqual(["STU-1001"], [student.student_number for student in search_results])
        self.assertEqual(INACTIVE_STATUS, inactive.status)
        self.assertEqual(["STU-1002"], [student.student_number for student in active_students])
        self.assertEqual(
            ["STU-1002", "STU-1001"],
            [student.student_number for student in all_students],
        )
        self.assertEqual(first.student_id, active_again.student_id)
        self.assertEqual(ACTIVE_STATUS, active_again.status)
        self.assertEqual(2, student_count)


if __name__ == "__main__":
    unittest.main()
