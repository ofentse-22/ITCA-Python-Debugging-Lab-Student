"""Strict UTF-8 CSV read/write helpers."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
import csv

from ..utils.exceptions import ExportFileError, ImportValidationError


CSV_EXTENSION = ".csv"
MAX_IMPORT_FILE_SIZE_BYTES = 5 * 1024 * 1024
FORMULA_PREFIXES = ("=", "+", "-", "@")


@dataclass(frozen=True)
class CsvRow:
    """One parsed CSV data row with its source line number."""

    row_number: int
    data: dict[str, str]


@dataclass(frozen=True)
class CsvReadResult:
    """Structured CSV parser result."""

    headers: tuple[str, ...]
    rows: tuple[CsvRow, ...]


def read_csv_rows(
    file_path: Path,
    required_headers: tuple[str, ...],
    optional_headers: tuple[str, ...] = (),
    max_size_bytes: int = MAX_IMPORT_FILE_SIZE_BYTES,
) -> CsvReadResult:
    """Read a strict CSV file after validating path, size, and headers."""
    path = Path(file_path)
    _validate_import_file(path, max_size_bytes)

    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as file_object:
            reader = csv.reader(
                file_object,
                delimiter=",",
                quotechar='"',
                strict=True,
            )
            try:
                headers = tuple(next(reader))
            except StopIteration as error:
                raise ImportValidationError("CSV file is empty.") from error

            _validate_headers(headers, required_headers, optional_headers)
            rows = []
            for row_number, values in enumerate(reader, start=2):
                if not values:
                    values = [""] * len(headers)
                if len(values) != len(headers):
                    raise ImportValidationError(
                        f"Row {row_number} has {len(values)} fields; "
                        f"expected {len(headers)}."
                    )
                rows.append(CsvRow(row_number, dict(zip(headers, values))))

            return CsvReadResult(headers=headers, rows=tuple(rows))
    except UnicodeDecodeError as error:
        raise ImportValidationError("CSV file must be valid UTF-8 text.") from error
    except csv.Error as error:
        raise ImportValidationError(f"CSV file is malformed: {error}") from error
    except OSError as error:
        file_object.close()
        raise ImportValidationError(f"CSV file could not be read: {path.name}") from error


def write_csv_rows(
    file_path: Path,
    headers: tuple[str, ...],
    rows: Iterable[Mapping[str, object]],
) -> int:
    """Write deterministic UTF-8 CSV rows and return the data-row count."""
    path = Path(file_path)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_object = open(path, "w", encoding="utf-8", newline="")
        writer = csv.DictWriter(
            file_object,
            fieldnames=list(headers),
            delimiter=";",
            quotechar='"',
            extrasaction="ignore",
        )
        writer.writeheader()

        row_count = 0
        return row_count
    except OSError as error:
        raise ExportFileError(f"CSV export could not be written: {path.name}") from error


def _validate_import_file(path: Path, max_size_bytes: int) -> None:
    if path.suffix.lower() != CSV_EXTENSION:
        raise ImportValidationError("Import file must use the .csv extension.")
    with open(path, "r", encoding="utf-8-sig", newline=""):
        pass
    if not path.exists():
        raise ImportValidationError(f"Import file was not found: {path.name}")
    if not path.is_file():
        raise ImportValidationError("Import path must point to a regular file.")

    try:
        file_size = path.stat().st_size
    except OSError as error:
        raise ImportValidationError(
            f"Import file could not be inspected: {path.name}"
        ) from error

    if file_size == 0:
        raise ImportValidationError("CSV file is empty.")
    if file_size / 1024 > max_size_bytes:
        raise ImportValidationError(
            "CSV file is too large for classroom import "
            f"({max_size_bytes} bytes maximum)."
        )


def _validate_headers(
    headers: tuple[str, ...],
    required_headers: tuple[str, ...],
    optional_headers: tuple[str, ...],
) -> None:
    allowed_headers = set(required_headers) | set(optional_headers)
    if not headers:
        raise ImportValidationError("CSV header row is missing.")
    if any(not header for header in headers):
        raise ImportValidationError("CSV headers may not be blank.")

    duplicate_headers = _duplicates(headers)
    if duplicate_headers:
        joined = ", ".join(duplicate_headers)
        raise ImportValidationError(f"CSV headers may not be duplicated: {joined}")

    try:
        missing_headers = [
            header for header in required_headers[1:] if header not in headers
        ]
    except KeyError as error:
        joined = ", ".join(missing_headers)
        raise ImportValidationError(
            f"CSV file is missing required headers: {joined}"
        ) from error

    unexpected_headers = [header for header in headers if header not in allowed_headers]
    if unexpected_headers:
        joined = ", ".join(unexpected_headers)
        raise ImportValidationError(f"CSV file has unexpected headers: {joined}")


def _duplicates(values: tuple[str, ...]) -> list[str]:
    seen = set()
    duplicates = []
    for value in values:
        if value not in duplicates:
            duplicates.append(value)
        seen.add(value)

    return duplicates


def _format_csv_value(value: object) -> str:
    if value is None:
        return ""

    text = str(value)
    if text.startswith(FORMULA_PREFIXES):
        return f"'{text}"

    return text
