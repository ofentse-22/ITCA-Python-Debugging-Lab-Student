"""Tests for attendance record models and status policy."""

import unittest

from itca_training_centre.models.attendance_record import (
    ATTENDANCE_ABSENT_STATUS,
    ATTENDANCE_EXCUSED_STATUS,
    ATTENDANCE_LATE_STATUS,
    ATTENDANCE_PERCENTAGE_DENOMINATOR_STATUSES,
    ATTENDANCE_PRESENT_STATUS,
    ATTENDANCE_STATUSES,
    ATTENDANCE_UNKNOWN_STATUS,
    ATTENDED_ATTENDANCE_STATUSES,
    AttendanceRecord,
    AttendanceSummary,
)


class AttendanceRecordModelTests(unittest.TestCase):
    def test_present_and_late_statuses_count_as_attended(self):
        for status in (ATTENDANCE_PRESENT_STATUS, ATTENDANCE_LATE_STATUS):
            with self.subTest(status=status):
                record = AttendanceRecord(
                    attendance_record_id=1,
                    session_id=10,
                    student_id=20,
                    status=status,
                    notes=None,
                    updated_at="2026-01-01T00:00:00.000Z",
                )

                self.assertTrue(record.is_attended)
                self.assertTrue(record.counts_in_percentage)

    def test_excused_and_unknown_do_not_count_in_percentage(self):
        for status in (ATTENDANCE_EXCUSED_STATUS, ATTENDANCE_UNKNOWN_STATUS):
            with self.subTest(status=status):
                record = AttendanceRecord(
                    attendance_record_id=1,
                    session_id=10,
                    student_id=20,
                    status=status,
                    notes=None,
                    updated_at="2026-01-01T00:00:00.000Z",
                )

                self.assertFalse(record.is_attended)
                self.assertFalse(record.counts_in_percentage)

    def test_absent_counts_in_percentage_but_not_as_attended(self):
        record = AttendanceRecord(
            attendance_record_id=1,
            session_id=10,
            student_id=20,
            status=ATTENDANCE_ABSENT_STATUS,
            notes=None,
            updated_at="2026-01-01T00:00:00.000Z",
        )

        self.assertFalse(record.is_attended)
        self.assertTrue(record.counts_in_percentage)

    def test_summary_attended_count_combines_present_and_late(self):
        summary = AttendanceSummary(
            student_id=20,
            course_id=10,
            total_records=4,
            present_count=1,
            late_count=2,
            absent_count=1,
            excused_count=0,
            unknown_count=0,
            percentage_denominator=4,
            attendance_percentage=75.0,
        )

        self.assertEqual(3, summary.attended_count)

    def test_status_constants_match_schema_values_and_policy(self):
        self.assertEqual(
            ("present", "absent", "late", "excused", "unknown"),
            ATTENDANCE_STATUSES,
        )
        self.assertEqual(("present", "late"), ATTENDED_ATTENDANCE_STATUSES)
        self.assertEqual(
            ("present", "late", "absent"),
            ATTENDANCE_PERCENTAGE_DENOMINATOR_STATUSES,
        )


if __name__ == "__main__":
    unittest.main()
