"""Tests for configuration settings."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from itca_training_centre.config.settings import (
    ensure_runtime_directories,
    load_config,
)
from itca_training_centre.utils.exceptions import ConfigurationError


class SettingsTests(unittest.TestCase):
    def test_default_config_uses_controlled_runtime_paths(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            config = load_config(project_root=project_root)

            self.assertEqual(
                "ITCA Training Centre Management System",
                config.application_name,
            )
            self.assertTrue(config.paths.runtime_dir.is_relative_to(project_root))
            self.assertTrue(config.paths.database_path.is_relative_to(project_root))
            self.assertTrue(config.paths.import_dir.is_relative_to(project_root))
            self.assertTrue(config.paths.export_dir.is_relative_to(project_root))
            self.assertFalse(config.paths.database_path.exists())

    def test_ensure_runtime_directories_creates_only_required_directories(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config = load_config(project_root=project_root)

            created = ensure_runtime_directories(config)

            self.assertEqual(set(config.paths.required_directories()), set(created))
            for directory in config.paths.required_directories():
                self.assertTrue(directory.exists())
                self.assertTrue(directory.is_dir())
            self.assertFalse(config.paths.database_path.exists())

    def test_valid_json_config_can_override_names_and_runtime_folder(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_file = project_root / "runtime" / "config.json"
            config_file.parent.mkdir()
            config_file.write_text(
                json.dumps(
                    {
                        "config_format_version": 1,
                        "application": {
                            "name": "Training Centre Test App",
                            "version": "9.9.9",
                        },
                        "runtime": {
                            "directory": "test_runtime",
                            "data_directory": "test_data",
                            "import_directory": "test_imports",
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(project_root=project_root, config_path=config_file)

            self.assertEqual("Training Centre Test App", config.application_name)
            self.assertEqual("9.9.9", config.version)
            self.assertEqual(project_root / "test_runtime", config.paths.runtime_dir)
            self.assertEqual(
                project_root / "test_runtime" / "test_data",
                config.paths.data_dir,
            )
            self.assertEqual(
                project_root / "test_runtime" / "test_imports",
                config.paths.import_dir,
            )

    def test_invalid_json_raises_configuration_error(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_file = project_root / "runtime" / "config.json"
            config_file.parent.mkdir()
            config_file.write_text("{invalid json", encoding="utf-8")

            with self.assertRaises(ConfigurationError):
                load_config(project_root=project_root, config_path=config_file)

    def test_empty_and_wrong_shape_config_files_are_rejected(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_file = project_root / "runtime" / "config.json"
            config_file.parent.mkdir()

            config_file.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "invalid JSON"):
                load_config(project_root=project_root, config_path=config_file)

            config_file.write_text(json.dumps([]), encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "JSON object"):
                load_config(project_root=project_root, config_path=config_file)

            config_file.write_text(json.dumps({"runtime": []}), encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "runtime"):
                load_config(project_root=project_root, config_path=config_file)

    def test_unsupported_config_format_version_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_file = project_root / "runtime" / "config.json"
            config_file.parent.mkdir()
            config_file.write_text(
                json.dumps({"config_format_version": 2}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigurationError, "Unsupported"):
                load_config(project_root=project_root, config_path=config_file)

    def test_unknown_config_key_raises_configuration_error(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_file = project_root / "runtime" / "config.json"
            config_file.parent.mkdir()
            config_file.write_text(
                json.dumps({"unexpected": True}),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_config(project_root=project_root, config_path=config_file)

    def test_unsafe_runtime_path_raises_configuration_error(self):
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_file = project_root / "runtime" / "config.json"
            config_file.parent.mkdir()
            config_file.write_text(
                json.dumps({"runtime": {"directory": "../outside"}}),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_config(project_root=project_root, config_path=config_file)


if __name__ == "__main__":
    unittest.main()
