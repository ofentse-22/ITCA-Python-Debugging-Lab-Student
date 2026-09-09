"""Persistence operations for trainers."""

from pathlib import Path
import sqlite3

from ..data.connection import open_database, transaction
from ..models.trainer import (
    TRAINER_ACTIVE_STATUS,
    TRAINER_INACTIVE_STATUS,
    TRAINER_STATUSES,
    Trainer,
)
from ..utils.exceptions import DatabaseError, DuplicateRecordError


TRAINER_COLUMNS = """
trainer_id,
trainer_number,
first_name,
last_name,
email,
phone,
status,
created_at,
updated_at
"""

TRAINER_ORDER_BY = "lower(last_name), lower(first_name), lower(trainer_number)"


class TrainerRepository:
    """SQLite-backed repository for trainer records."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def create(
        self,
        trainer_number: str,
        first_name: str,
        last_name: str,
        email: str | None,
        phone: str | None,
        status: str = TRAINER_ACTIVE_STATUS,
    ) -> Trainer:
        """Insert and return a new trainer."""
        with open_database(self.database_path) as connection:
            with transaction(connection):
                cursor = connection.execute(
                    """
                    INSERT INTO trainers (
                        trainer_number,
                        first_name,
                        last_name,
                        email,
                        phone,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trainer_number,
                        first_name,
                        last_name,
                        email,
                        phone,
                        status,
                    ),
                )
                trainer_id = cursor.lastrowid

            try:
                return self._get_by_id_in_connection(connection, trainer_id)
            except sqlite3.IntegrityError as error:
                raise _trainer_constraint_error(error) from error
            except sqlite3.Error as error:
                raise DatabaseError("Trainer could not be created.") from error

    def get_by_id(self, trainer_id: int) -> Trainer | None:
        """Return a trainer by primary key, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                return self._get_optional_by_id_in_connection(connection, trainer_id)
        except sqlite3.Error as error:
            raise DatabaseError("Trainer could not be retrieved.") from error

    def get_by_number(self, trainer_number: str) -> Trainer | None:
        """Return a trainer by trainer number, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT {TRAINER_COLUMNS}
                    FROM trainers
                    WHERE trainer_number = ?
                    """,
                    (trainer_number,),
                ).fetchone()

            return _trainer_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Trainer could not be retrieved.") from error

    def list_trainers(self, include_inactive: bool = False) -> list[Trainer]:
        """Return trainers in deterministic display order."""
        try:
            with open_database(self.database_path) as connection:
                if include_inactive:
                    rows = connection.execute(
                        f"""
                        SELECT {TRAINER_COLUMNS}
                        FROM trainers
                        ORDER BY {TRAINER_ORDER_BY}
                        """
                    ).fetchall()
                else:
                    rows = connection.execute(
                        f"""
                        SELECT {TRAINER_COLUMNS}
                        FROM trainers
                        WHERE status = ?
                        ORDER BY {TRAINER_ORDER_BY}
                        """,
                        (TRAINER_ACTIVE_STATUS,),
                    ).fetchall()

            return [_trainer_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Trainers could not be listed.") from error

    def search(self, search_text: str, include_inactive: bool = False) -> list[Trainer]:
        """Search by trainer number, name, combined name, or email."""
        pattern = _like_pattern(search_text)
        where_clause = """
            (
                trainer_number LIKE ? ESCAPE '\\'
                OR first_name LIKE ? ESCAPE '\\'
                OR last_name LIKE ? ESCAPE '\\'
                OR (first_name || ' ' || last_name) LIKE ? ESCAPE '\\'
                OR COALESCE(email, '') LIKE ? ESCAPE '\\'
            )
        """
        parameters: list[str] = [pattern, pattern, pattern, pattern, pattern]

        if not include_inactive:
            where_clause += " AND status = ?"
            parameters.append(TRAINER_ACTIVE_STATUS)

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT {TRAINER_COLUMNS}
                    FROM trainers
                    WHERE {where_clause}
                    ORDER BY {TRAINER_ORDER_BY}
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_trainer_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Trainers could not be searched.") from error

    def update(
        self,
        trainer_id: int,
        first_name: str,
        last_name: str,
        email: str | None,
        phone: str | None,
    ) -> Trainer | None:
        """Update mutable trainer fields and return the updated trainer."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE trainers
                        SET first_name = ?,
                            last_name = ?,
                            email = ?,
                            phone = ?,
                            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        WHERE trainer_id = ?
                        """,
                        (first_name, last_name, email, phone, trainer_id),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, trainer_id)
        except sqlite3.IntegrityError as error:
            raise _trainer_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Trainer could not be updated.") from error

    def deactivate(self, trainer_id: int) -> Trainer | None:
        """Mark a trainer inactive without physically deleting the record."""
        return self._set_status(trainer_id, TRAINER_INACTIVE_STATUS)

    def reactivate(self, trainer_id: int) -> Trainer | None:
        """Mark a trainer active again using the same stored record."""
        return self._set_status(trainer_id, TRAINER_ACTIVE_STATUS)

    def _set_status(self, trainer_id: int, status: str) -> Trainer | None:
        if status not in TRAINER_STATUSES:
            raise ValueError(f"Unsupported trainer status: {status}")

        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE trainers
                        SET status = ?,
                            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                        WHERE trainer_id = ?
                        """,
                        (status, trainer_id),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, trainer_id)
        except sqlite3.Error as error:
            raise DatabaseError("Trainer status could not be changed.") from error

    def _get_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        trainer_id: int,
    ) -> Trainer:
        trainer = self._get_optional_by_id_in_connection(connection, trainer_id)
        if trainer is None:
            raise DatabaseError("Created trainer could not be retrieved.")

        return trainer

    def _get_optional_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        trainer_id: int,
    ) -> Trainer | None:
        row = connection.execute(
            f"""
            SELECT {TRAINER_COLUMNS}
            FROM trainers
            WHERE trainer_id = ?
            """,
            (trainer_id,),
        ).fetchone()
        return _trainer_from_row(row) if row is not None else None


def _trainer_from_row(row) -> Trainer:
    return Trainer(
        trainer_id=row["trainer_id"],
        trainer_number=row["trainer_number"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        email=row["email"],
        phone=row["phone"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _trainer_constraint_error(error: sqlite3.IntegrityError):
    message = str(error)
    if "trainers.trainer_number" in message:
        return DuplicateRecordError("Trainer number already exists.")
    if "trainers.email" in message:
        return DuplicateRecordError("Email address already exists.")

    return DatabaseError("Trainer data violated a database constraint.")


def _like_pattern(search_text: str) -> str:
    escaped = (
        search_text.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"
