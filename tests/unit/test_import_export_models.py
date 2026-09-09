"""Tests for import/export read models."""

from pathlib import Path
import unittest

from itca_training_centre.models.import_export import (
    IMPORT_STUDENTS,
    ISSUE_CONFLICT,
    ImportPreview,
    ImportRowIssue,
    StudentImportRow,
)


class ImportExportModelTests(unittest.TestCase):
    def test_preview_counts_valid_invalid_and_conflict_rows(self):
        preview = ImportPreview(
            import_type=IMPORT_STUDENTS,
            source_path=Path("students.csv"),
            total_rows=4,
            rows=(
                StudentImportRow("STU-001", "Amina", "Nkosi", None, None),
            ),
            issues=(
                ImportRowIssue(3, "email", "Email must contain one @ symbol."),
                ImportRowIssue(3, "first_name", "First name is required."),
                ImportRowIssue(
                    4,
                    "student_number",
                    "Student number already exists.",
                    ISSUE_CONFLICT,
                ),
            ),
        )

        self.assertEqual(1, preview.valid_row_count)
        self.assertEqual(1, preview.rows_to_create)
        self.assertEqual(1, preview.invalid_row_count)
        self.assertEqual(1, preview.conflict_count)
        self.assertTrue(preview.has_issues)
        self.assertFalse(preview.is_importable)

    def test_header_only_preview_is_importable_but_creates_nothing(self):
        preview = ImportPreview(
            import_type=IMPORT_STUDENTS,
            source_path=Path("students.csv"),
            total_rows=0,
        )

        self.assertEqual(0, preview.valid_row_count)
        self.assertEqual(0, preview.rows_to_create)
        self.assertFalse(preview.has_issues)
        self.assertTrue(preview.is_importable)

    def test_fatal_preview_blocks_import(self):
        preview = ImportPreview(
            import_type=IMPORT_STUDENTS,
            source_path=Path("students.csv"),
            total_rows=0,
            fatal_error="CSV file is empty.",
        )

        self.assertTrue(preview.has_fatal_error)
        self.assertTrue(preview.has_issues)
        self.assertFalse(preview.is_importable)


if __name__ == "__main__":
    unittest.main()
