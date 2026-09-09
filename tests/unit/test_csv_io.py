"""Tests for strict CSV file helpers."""

from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import unittest

from itca_training_centre.storage.csv_io import read_csv_rows, write_csv_rows
from itca_training_centre.utils.exceptions import ExportFileError, ImportValidationError


class CsvIoTests(unittest.TestCase):
    def test_read_csv_handles_utf8_quotes_commas_and_newlines(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "students.csv"
            path.write_text(
                'student_number,first_name,last_name,email,phone\n'
                'STU-001,"Ama,hle",Nkosi,amahlé@example.edu,"Line one\nLine two"\n',
                encoding="utf-8",
                newline="",
            )

            result = read_csv_rows(
                path,
                ("student_number", "first_name", "last_name", "email", "phone"),
            )

        self.assertEqual(
            ("student_number", "first_name", "last_name", "email", "phone"),
            result.headers,
        )
        self.assertEqual(2, result.rows[0].row_number)
        self.assertEqual("Ama,hle", result.rows[0].data["first_name"])
        self.assertEqual("amahlé@example.edu", result.rows[0].data["email"])
        self.assertEqual("Line one\nLine two", result.rows[0].data["phone"])

    def test_read_csv_accepts_optional_utf8_bom_on_header_row(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "students.csv"
            path.write_bytes(
                b"\xef\xbb\xbfstudent_number,first_name\nSTU-001,Amina\n"
            )

            result = read_csv_rows(path, ("student_number", "first_name"))

        self.assertEqual(("student_number", "first_name"), result.headers)
        self.assertEqual("STU-001", result.rows[0].data["student_number"])

    def test_write_csv_uses_deterministic_headers_and_formula_safety(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "students.csv"

            count = write_csv_rows(
                path,
                ("student_number", "first_name", "last_name", "email", "phone"),
                [
                    {
                        "student_number": "STU-001",
                        "first_name": "=A1",
                        "last_name": "Comma, Name",
                        "email": None,
                        "phone": "@call",
                    }
                ],
            )

            raw_text = path.read_text(encoding="utf-8")
            with open(path, "r", encoding="utf-8", newline="") as file_object:
                rows = list(csv.reader(file_object))

        self.assertEqual(1, count)
        self.assertNotIn("\r\r\n", raw_text)
        self.assertEqual(
            ["student_number", "first_name", "last_name", "email", "phone"],
            rows[0],
        )
        self.assertEqual("'=A1", rows[1][1])
        self.assertEqual("Comma, Name", rows[1][2])
        self.assertEqual("", rows[1][3])
        self.assertEqual("'@call", rows[1][4])

    def test_read_csv_rejects_missing_directory_empty_and_wrong_extension(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            headers = ("student_number",)
            empty = temp_path / "empty.csv"
            empty.write_text("", encoding="utf-8")
            csv_directory = temp_path / "incoming.csv"
            csv_directory.mkdir()
            text_file = temp_path / "students.txt"
            text_file.write_text("student_number\nSTU-001\n", encoding="utf-8")

            with self.assertRaisesRegex(ImportValidationError, "not found"):
                read_csv_rows(temp_path / "missing.csv", headers)
            with self.assertRaisesRegex(ImportValidationError, "regular file"):
                read_csv_rows(csv_directory, headers)
            with self.assertRaisesRegex(ImportValidationError, ".csv"):
                read_csv_rows(text_file, headers)
            with self.assertRaisesRegex(ImportValidationError, "empty"):
                read_csv_rows(empty, headers)

    def test_read_csv_rejects_invalid_encoding_and_oversized_files(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            invalid_utf8 = temp_path / "invalid.csv"
            invalid_utf8.write_bytes(b"student_number\n\xff\n")
            oversized = temp_path / "oversized.csv"
            oversized.write_text("student_number\nSTU-001\n", encoding="utf-8")

            with self.assertRaisesRegex(ImportValidationError, "UTF-8"):
                read_csv_rows(invalid_utf8, ("student_number",))
            with self.assertRaisesRegex(ImportValidationError, "too large"):
                read_csv_rows(oversized, ("student_number",), max_size_bytes=1)

    def test_read_csv_rejects_bad_headers_and_malformed_rows(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            required = ("student_number", "first_name")
            cases = {
                "missing.csv": "student_number\nSTU-001\n",
                "duplicate.csv": "student_number,student_number,first_name\nA,B,C\n",
                "extra.csv": "student_number,first_name,unknown\nA,B,C\n",
                "ragged.csv": "student_number,first_name\nSTU-001\n",
                "malformed.csv": 'student_number,first_name\n"STU-001,Amina\n',
            }

            for filename, text in cases.items():
                path = temp_path / filename
                path.write_text(text, encoding="utf-8", newline="")

            with self.assertRaisesRegex(ImportValidationError, "missing"):
                read_csv_rows(temp_path / "missing.csv", required)
            with self.assertRaisesRegex(ImportValidationError, "duplicated"):
                read_csv_rows(temp_path / "duplicate.csv", required)
            with self.assertRaisesRegex(ImportValidationError, "unexpected"):
                read_csv_rows(temp_path / "extra.csv", required)
            with self.assertRaisesRegex(ImportValidationError, "expected 2"):
                read_csv_rows(temp_path / "ragged.csv", required)
            with self.assertRaisesRegex(ImportValidationError, "malformed"):
                read_csv_rows(temp_path / "malformed.csv", required)

    def test_write_csv_reports_output_errors(self):
        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(ExportFileError):
                write_csv_rows(Path(temp_dir), ("name",), [{"name": "Amina"}])


if __name__ == "__main__":
    unittest.main()
