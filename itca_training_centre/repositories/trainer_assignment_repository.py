"""Persistence operations for trainer assignments."""

from pathlib import Path
import sqlite3

from ..data.connection import open_database, transaction
from ..models.trainer_assignment import (
    ASSIGNMENT_ACTIVE_STATUS,
    ASSIGNMENT_ENDED_STATUS,
    ASSIGNMENT_STATUSES,
    TrainerAssignment,
)
from ..utils.exceptions import DatabaseError, DuplicateRecordError, RecordNotFoundError


ASSIGNMENT_COLUMNS = """
assignment_id,
trainer_id,
course_id,
assigned_from,
assigned_to,
status
"""


class TrainerAssignmentRepository:
    """SQLite-backed repository for trainer-course assignments."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def create(
        self,
        trainer_id: int,
        course_id: int,
        assigned_from: str,
        assigned_to: str | None = None,
        status: str = ASSIGNMENT_ACTIVE_STATUS,
    ) -> TrainerAssignment:
        """Insert and return a trainer-course assignment."""
        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        INSERT INTO trainer_assignments (
                            trainer_id,
                            course_id,
                            assigned_from,
                            assigned_to,
                            status
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (trainer_id, course_id, assigned_from, assigned_to, status),
                    )
                    assignment_id = cursor.lastrowid

                return self._get_by_id_in_connection(connection, assignment_id)
        except sqlite3.IntegrityError as error:
            raise _assignment_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Trainer assignment could not be created.") from error

    def get_by_id(self, assignment_id: int) -> TrainerAssignment | None:
        """Return an assignment by primary key, or None when missing."""
        try:
            with open_database(self.database_path) as connection:
                return self._get_optional_by_id_in_connection(connection, assignment_id)
        except sqlite3.Error as error:
            raise DatabaseError("Trainer assignment could not be retrieved.") from error

    def get_active_for_trainer_course(
        self,
        trainer_id: int,
        course_id: int,
    ) -> TrainerAssignment | None:
        """Return the active assignment for one trainer/course pair."""
        return self._get_for_trainer_course(
            trainer_id=trainer_id,
            course_id=course_id,
            status=ASSIGNMENT_ACTIVE_STATUS,
        )

    def get_latest_for_trainer_course(
        self,
        trainer_id: int,
        course_id: int,
    ) -> TrainerAssignment | None:
        """Return the most recent assignment for one trainer/course pair."""
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT {ASSIGNMENT_COLUMNS}
                    FROM trainer_assignments
                    WHERE trainer_id = ?
                      AND course_id = ?
                    ORDER BY assignment_id DESC
                    LIMIT 1
                    """,
                    (trainer_id, course_id),
                ).fetchone()

            return _assignment_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Trainer assignment could not be retrieved.") from error

    def list_assignments(
        self,
        include_ended: bool = False,
        status: str | None = None,
    ) -> list[TrainerAssignment]:
        """Return assignments in a deterministic cross-course order."""
        where_parts: list[str] = []
        parameters: list[str] = []
        _append_assignment_status_filter(where_parts, parameters, include_ended, status)

        return self._list_joined(
            where_parts=where_parts,
            parameters=parameters,
            order_by=(
                "lower(c.course_code), lower(t.last_name), "
                "lower(t.first_name), lower(t.trainer_number), "
                "a.assigned_from, a.assignment_id"
            ),
        )

    def list_for_trainer(
        self,
        trainer_id: int,
        include_ended: bool = False,
        status: str | None = None,
    ) -> list[TrainerAssignment]:
        """Return assignments for one trainer ordered by course."""
        where_parts = ["a.trainer_id = ?"]
        parameters: list[int | str] = [trainer_id]
        _append_assignment_status_filter(where_parts, parameters, include_ended, status)

        return self._list_joined(
            where_parts=where_parts,
            parameters=parameters,
            order_by="lower(c.course_code), a.assigned_from, a.assignment_id",
        )

    def list_for_course(
        self,
        course_id: int,
        include_ended: bool = False,
        status: str | None = None,
    ) -> list[TrainerAssignment]:
        """Return assignments for one course ordered by trainer name."""
        where_parts = ["a.course_id = ?"]
        parameters: list[int | str] = [course_id]
        _append_assignment_status_filter(where_parts, parameters, include_ended, status)

        return self._list_joined(
            where_parts=where_parts,
            parameters=parameters,
            order_by=(
                "lower(t.last_name), lower(t.first_name), "
                "lower(t.trainer_number), a.assigned_from, a.assignment_id"
            ),
        )

    def list_for_trainer_course(
        self,
        trainer_id: int,
        course_id: int,
        include_ended: bool = False,
        status: str | None = None,
    ) -> list[TrainerAssignment]:
        """Return assignments for one trainer/course pair ordered by date."""
        where_parts = ["a.trainer_id = ?", "a.course_id = ?"]
        parameters: list[int | str] = [trainer_id, course_id]
        _append_assignment_status_filter(where_parts, parameters, include_ended, status)

        return self._list_joined(
            where_parts=where_parts,
            parameters=parameters,
            order_by="a.assigned_from, a.assignment_id",
        )

    def end(self, assignment_id: int, assigned_to: str | None = None) -> TrainerAssignment | None:
        """End an assignment while preserving the historical row."""
        return self._set_status(
            assignment_id=assignment_id,
            status=ASSIGNMENT_ENDED_STATUS,
            assigned_to=assigned_to,
        )

    def reactivate(self, assignment_id: int) -> TrainerAssignment | None:
        """Set an ended assignment back to active using the same stored record."""
        return self._set_status(
            assignment_id=assignment_id,
            status=ASSIGNMENT_ACTIVE_STATUS,
            assigned_to=None,
        )

    def _get_for_trainer_course(
        self,
        trainer_id: int,
        course_id: int,
        status: str,
    ) -> TrainerAssignment | None:
        try:
            with open_database(self.database_path) as connection:
                row = connection.execute(
                    f"""
                    SELECT {ASSIGNMENT_COLUMNS}
                    FROM trainer_assignments
                    WHERE trainer_id = ?
                      AND course_id = ?
                      AND status = ?
                    ORDER BY assignment_id DESC
                    LIMIT 1
                    """,
                    (trainer_id, course_id, status),
                ).fetchone()

            return _assignment_from_row(row) if row is not None else None
        except sqlite3.Error as error:
            raise DatabaseError("Trainer assignment could not be retrieved.") from error

    def _set_status(
        self,
        assignment_id: int,
        status: str,
        assigned_to: str | None,
    ) -> TrainerAssignment | None:
        if status not in ASSIGNMENT_STATUSES:
            raise ValueError(f"Unsupported assignment status: {status}")

        try:
            with open_database(self.database_path) as connection:
                with transaction(connection):
                    cursor = connection.execute(
                        """
                        UPDATE trainer_assignments
                        SET status = ?,
                            assigned_to = ?
                        WHERE assignment_id = ?
                        """,
                        (status, assigned_to, assignment_id),
                    )

                if cursor.rowcount == 0:
                    return None

                return self._get_optional_by_id_in_connection(connection, assignment_id)
        except sqlite3.IntegrityError as error:
            raise _assignment_constraint_error(error) from error
        except sqlite3.Error as error:
            raise DatabaseError("Trainer assignment status could not be changed.") from error

    def _list_joined(
        self,
        where_parts: list[str],
        parameters: list[int | str],
        order_by: str,
    ) -> list[TrainerAssignment]:
        where_clause = ""
        if where_parts:
            where_clause = f"WHERE {' AND '.join(where_parts)}"

        try:
            with open_database(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        a.assignment_id,
                        a.trainer_id,
                        a.course_id,
                        a.assigned_from,
                        a.assigned_to,
                        a.status
                    FROM trainer_assignments a
                    JOIN trainers t ON t.trainer_id = a.trainer_id
                    JOIN courses c ON c.course_id = a.course_id
                    {where_clause}
                    ORDER BY {order_by}
                    """,
                    tuple(parameters),
                ).fetchall()

            return [_assignment_from_row(row) for row in rows]
        except sqlite3.Error as error:
            raise DatabaseError("Trainer assignments could not be listed.") from error

    def _get_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        assignment_id: int,
    ) -> TrainerAssignment:
        assignment = self._get_optional_by_id_in_connection(connection, assignment_id)
        if assignment is None:
            raise DatabaseError("Created trainer assignment could not be retrieved.")

        return assignment

    def _get_optional_by_id_in_connection(
        self,
        connection: sqlite3.Connection,
        assignment_id: int,
    ) -> TrainerAssignment | None:
        row = connection.execute(
            f"""
            SELECT {ASSIGNMENT_COLUMNS}
            FROM trainer_assignments
            WHERE assignment_id = ?
            """,
            (assignment_id,),
        ).fetchone()
        return _assignment_from_row(row) if row is not None else None


def _assignment_from_row(row) -> TrainerAssignment:
    return TrainerAssignment(
        assignment_id=row["assignment_id"],
        trainer_id=row["trainer_id"],
        course_id=row["course_id"],
        assigned_from=row["assigned_from"],
        assigned_to=row["assigned_to"],
        status=row["status"],
    )


def _assignment_constraint_error(error: sqlite3.IntegrityError):
    message = str(error)
    if "trainer_assignments.trainer_id, trainer_assignments.course_id" in message:
        return DuplicateRecordError(
            "Trainer is already actively assigned to this course."
        )
    if "FOREIGN KEY constraint failed" in message:
        return RecordNotFoundError(
            "Trainer or course was not found for this assignment operation."
        )

    return DatabaseError("Trainer assignment data violated a database constraint.")


def _append_assignment_status_filter(
    where_parts: list[str],
    parameters: list[int | str],
    include_ended: bool,
    status: str | None,
) -> None:
    if status is not None:
        where_parts.append("a.status = ?")
        parameters.append(status)
    elif not include_ended:
        where_parts.append("a.status = ?")
        parameters.append(ASSIGNMENT_ACTIVE_STATUS)
