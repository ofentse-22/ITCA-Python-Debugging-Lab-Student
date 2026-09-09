"""Helpers for keeping generated files inside controlled directories."""

from pathlib import Path

from .exceptions import PathSafetyError


def resolve_relative_path(base_dir: Path, candidate_path: Path | str) -> Path:
    """Resolve a relative path under base_dir and reject unsafe paths."""
    base = Path(base_dir).resolve()
    candidate = Path(candidate_path)

    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        _reject_parent_traversal(candidate)
        resolved = (base / candidate).resolve()

    if not resolved.is_relative_to(base):
        raise PathSafetyError(f"Path is outside the controlled directory: {candidate}")

    if not candidate.is_absolute() and len(candidate.parts) > 1:
        raise PathSafetyError(
            f"Path must be directly inside the controlled directory: {candidate}"
        )

    return resolved


def ensure_directory_inside(base_dir: Path, directory_path: Path | str) -> Path:
    """Create a directory after confirming it is inside base_dir."""
    directory = resolve_relative_path(base_dir, directory_path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _reject_parent_traversal(candidate: Path) -> None:
    if ".." in candidate.parts:
        raise PathSafetyError(
            f"Path may not traverse outside the controlled directory: {candidate}"
        )
