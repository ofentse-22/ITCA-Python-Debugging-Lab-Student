"""Integration tests for explicit transaction behavior."""

import sqlite3
import unittest

from itca_training_centre.data.connection import open_database, transaction
from itca_training_centre.utils.exceptions import DatabaseError
from tests.helpers import temporary_database_path


class TransactionTests(unittest.TestCase):
    def test_transaction_commits_on_success(self):
        with temporary_database_path() as database_path:
            with open_database(database_path) as connection:
                connection.execute("CREATE TABLE example (name TEXT NOT NULL)")

                with transaction(connection):
                    connection.execute(
                        "INSERT INTO example (name) VALUES (?)",
                        ("committed",),
                    )

                count = connection.execute("SELECT COUNT(*) FROM example").fetchone()[0]

            self.assertEqual(1, count)

    def test_transaction_rolls_back_on_failure(self):
        with temporary_database_path() as database_path:
            with open_database(database_path) as connection:
                connection.execute("CREATE TABLE example (name TEXT NOT NULL UNIQUE)")

                with self.assertRaises(sqlite3.IntegrityError):
                    with transaction(connection):
                        connection.execute(
                            "INSERT INTO example (name) VALUES (?)",
                            ("duplicate",),
                        )
                        connection.execute(
                            "INSERT INTO example (name) VALUES (?)",
                            ("duplicate",),
                        )

                count = connection.execute("SELECT COUNT(*) FROM example").fetchone()[0]

            self.assertEqual(0, count)

    def test_nested_transaction_is_rejected(self):
        with temporary_database_path() as database_path:
            with open_database(database_path) as connection:
                with self.assertRaises(DatabaseError):
                    with transaction(connection):
                        with transaction(connection):
                            connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
