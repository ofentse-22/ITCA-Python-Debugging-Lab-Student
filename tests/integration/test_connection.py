"""Integration tests for SQLite connection configuration."""

import sqlite3
import unittest

from itca_training_centre.data.connection import open_connection, open_database
from tests.helpers import temporary_database_path


class ConnectionTests(unittest.TestCase):
    def test_connection_enables_foreign_keys_and_row_access(self):
        with temporary_database_path() as database_path:
            connection = open_connection(database_path)
            try:
                foreign_keys_enabled = connection.execute(
                    "PRAGMA foreign_keys"
                ).fetchone()[0]
                self.assertEqual(1, foreign_keys_enabled)

                connection.execute("CREATE TABLE example (name TEXT NOT NULL)")
                connection.execute("INSERT INTO example (name) VALUES (?)", ("Alice",))
                row = connection.execute("SELECT name FROM example").fetchone()

                self.assertEqual("Alice", row["name"])
            finally:
                connection.close()

    def test_open_database_closes_connection(self):
        with temporary_database_path() as database_path:
            with open_database(database_path) as connection:
                connection.execute("CREATE TABLE example (name TEXT NOT NULL)")

            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
