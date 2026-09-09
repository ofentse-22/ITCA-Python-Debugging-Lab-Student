"""Plain-text export helpers."""

from collections.abc import Iterable
from pathlib import Path

from ..utils.exceptions import ExportFileError


def write_text_file(file_path: Path, lines: Iterable[str]) -> int:
    """Write a UTF-8 text file and return the number of lines written."""
    path = Path(file_path)
    line_list = [str(line) for line in lines]

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as file_object:
            if line_list:
                file_object.write("\n".join(line_list))
                file_object.write("\n")
        return len(line_list)
    except OSError as error:
        raise ExportFileError(f"Text export could not be written: {path.name}") from error
