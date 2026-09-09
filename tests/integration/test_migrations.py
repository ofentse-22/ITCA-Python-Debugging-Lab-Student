"""Integration tests for migration behavior."""

import unittest

from itca_training_centre.data.connection import open_database
from itca_training_centre.data.migrations import initialize_database
from itca_training_centre.data.schema import MIGRATIONS
from itca_training_centre.utils.exceptions import UnsupportedSchemaVersionError
from tests.helpers import temporary_database_path


class MigrationTests(unittest.TestCase):
    def test_migrations_are_defined_in_ascending_order(self):
        versions = [migration.version for migration in MIGRATIONS]

        self.assertEqual(sorted(versions), versions)

    def test_same_migration_is_not_reapplied(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)
            initialize_database(database_path)

            with open_database(database_path) as connection:
                rows = connection.execute(
                    """
                    SELECT version, COUNT(*) AS migration_count
                    FROM schema_migrations
                    GROUP BY version
                    """
                ).fetchall()

            self.assertEqual(1, len(rows))
            self.assertEqual(1, rows[0]["version"])
            self.assertEqual(1, rows[0]["migration_count"])

    def test_newer_database_schema_is_rejected_safely(self):
        with temporary_database_path() as database_path:
            initialize_database(database_path)

            with open_database(database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO schema_migrations (version, name, applied_at)
                    VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    """,
                    (99, "future_schema",),
                )

            with self.assertRaises(UnsupportedSchemaVersionError):
                initialize_database(database_path)


if __name__ == "__main__":
    unittest.main()
