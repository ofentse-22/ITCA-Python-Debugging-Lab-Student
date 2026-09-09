"""Tests for controlled path helpers."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.utils.exceptions import PathSafetyError
from itca_training_centre.utils.path_safety import (
    ensure_directory_inside,
    resolve_relative_path,
)


class PathSafetyTests(unittest.TestCase):
    def test_resolve_relative_path_stays_inside_base(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            result = resolve_relative_path(base_dir, "runtime/logs")

            self.assertTrue(result.is_relative_to(base_dir.resolve()))

    def test_resolve_relative_path_rejects_parent_traversal(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            with self.assertRaises(PathSafetyError):
                resolve_relative_path(base_dir, "../outside")

    def test_resolve_relative_path_rejects_absolute_outside_path(self):
        with TemporaryDirectory() as base_temp, TemporaryDirectory() as outside_temp:
            base_dir = Path(base_temp)
            outside_path = Path(outside_temp)

            with self.assertRaises(PathSafetyError):
                resolve_relative_path(base_dir, outside_path)

    def test_ensure_directory_inside_creates_directory(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            result = ensure_directory_inside(base_dir, "runtime/logs")

            self.assertTrue(result.exists())
            self.assertTrue(result.is_dir())


if __name__ == "__main__":
    unittest.main()
