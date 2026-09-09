"""Shared test helpers."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


@contextmanager
def temporary_database_path() -> Iterator[Path]:
    """Yield an isolated database path that disappears after the test."""
    with TemporaryDirectory() as temp_dir:
        yield Path(temp_dir) / "runtime" / "data" / "test.sqlite3"
