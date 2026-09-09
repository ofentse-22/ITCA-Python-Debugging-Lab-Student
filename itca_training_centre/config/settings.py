"""Configuration loading and controlled runtime paths."""

from dataclasses import dataclass
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ..utils.exceptions import ConfigurationError, PathSafetyError
from ..utils.path_safety import ensure_directory_inside, resolve_relative_path
from . import defaults


@dataclass(frozen=True)
class RuntimePaths:
    """Controlled application paths derived from the project root."""

    project_root: Path
    runtime_dir: Path
    data_dir: Path
    log_dir: Path
    import_dir: Path
    export_dir: Path
    backup_dir: Path
    temp_dir: Path
    database_path: Path
    config_file: Path

    def required_directories(self) -> tuple[Path, ...]:
        """Return directories that must exist before the app can run."""
        return (
            self.runtime_dir,
            self.data_dir,
            self.log_dir,
            self.import_dir,
            self.export_dir,
            self.backup_dir,
            self.temp_dir,
        )


@dataclass(frozen=True)
class AppConfig:
    """Validated application configuration."""

    application_name: str
    version: str
    config_format_version: int
    paths: RuntimePaths


def load_config(
    project_root: Path | None = None,
    config_path: Path | None = None,
) -> AppConfig:
    """Load configuration from JSON when present, otherwise use defaults."""
    root = _resolve_project_root(project_root)
    default_config_path = root / defaults.RUNTIME_DIRECTORY / defaults.CONFIG_FILE_NAME
    active_config_path = _resolve_config_path(root, config_path or default_config_path)
    raw_config = _read_config_file(active_config_path)
    from .defaults import AppConfig as DefaultAppConfig

    try:
        return _build_config(root, active_config_path, raw_config)
    except PathSafetyError as error:
        raise ConfigurationError(str(error)) from error


def ensure_runtime_directories(config: AppConfig) -> tuple[Path, ...]:
    """Create required runtime directories inside the project root."""
    created = []
    for directory in config.paths.required_directories():
        created.append(ensure_directory_inside(config.paths.project_root, directory))

    return tuple(created)


def _resolve_project_root(project_root: Path | None) -> Path:
    if project_root is not None:
        return Path(project_root).resolve()

    return Path(__file__).resolve().parents[2]


def _resolve_config_path(project_root: Path, config_path: Path) -> Path:
    try:
        return resolve_relative_path(project_root, config_path)
    except PathSafetyError as error:
        raise ConfigurationError(str(error)) from error


def _read_config_file(config_file: Path) -> dict[str, Any]:
    if not config_file.exists():
        return {}

    try:
        with open(config_file, "r", encoding="utf-8") as file_object:
            raw_config = json.load(file_object)
    except JSONDecodeError as error:
        raise ConfigurationError(
            f"Configuration file is invalid JSON: {config_file}"
        ) from error
    except OSError as error:
        raise ConfigurationError(
            f"Configuration file could not be read: {config_file}"
        ) from error

    if not isinstance(raw_config, dict):
        raise ConfigurationError("Configuration root must be a JSON object.")

    return raw_config


def _build_config(
    project_root: Path,
    config_file: Path,
    raw_config: dict[str, Any],
) -> AppConfig:
    _reject_unknown_keys(raw_config, {"config_format_version", "application", "runtime"})

    config_format_version = _get_int(
        raw_config,
        "config_format_version",
        defaults.CONFIG_FORMAT_VERSION,
    )
    if config_format_version != defaults.CONFIG_FORMAT_VERSION:
        raise ConfigurationError(
            "Unsupported configuration format version: "
            f"{config_format_version}. This application supports version "
            f"{defaults.CONFIG_FORMAT_VERSION}."
        )

    application = _get_section(raw_config, "application")
    runtime = _get_section(raw_config, "runtime")

    _reject_unknown_keys(application, {"name", "version"})
    _reject_unknown_keys(
        runtime,
        {
            "directory",
            "data_directory",
            "log_directory",
            "import_directory",
            "export_directory",
            "backup_directory",
            "temp_directory",
            "database_file",
        },
    )

    application_name = _get_required_string(
        application,
        "name",
        defaults.APPLICATION_NAME,
    )
    version = _get_required_string(
        application,
        "version",
        defaults.APPLICATION_VERSION,
    )

    runtime_dir = resolve_relative_path(
        project_root,
        _get_required_string(runtime, "directory", defaults.RUNTIME_DIRECTORY),
    )
    data_dir = resolve_relative_path(
        runtime_dir,
        _get_required_string(runtime, "data_directory", defaults.DATA_DIRECTORY),
    )
    log_dir = resolve_relative_path(
        runtime_dir,
        _get_required_string(runtime, "log_directory", defaults.LOG_DIRECTORY),
    )
    import_dir = resolve_relative_path(
        runtime_dir,
        _get_required_string(runtime, "import_directory", defaults.IMPORT_DIRECTORY),
    )
    export_dir = resolve_relative_path(
        runtime_dir,
        _get_required_string(runtime, "export_directory", defaults.EXPORT_DIRECTORY),
    )
    backup_dir = resolve_relative_path(
        runtime_dir,
        _get_required_string(runtime, "backup_directory", defaults.BACKUP_DIRECTORY),
    )
    temp_dir = resolve_relative_path(
        runtime_dir,
        _get_required_string(runtime, "temp_directory", defaults.TEMP_DIRECTORY),
    )
    database_path = resolve_relative_path(
        data_dir,
        _get_required_string(runtime, "database_file", defaults.DATABASE_FILE_NAME),
    )

    paths = RuntimePaths(
        project_root=project_root,
        runtime_dir=runtime_dir,
        data_dir=data_dir,
        log_dir=log_dir,
        import_dir=import_dir,
        export_dir=export_dir,
        backup_dir=backup_dir,
        temp_dir=temp_dir,
        database_path=database_path,
        config_file=config_file,
    )

    return AppConfig(
        application_name=application_name,
        version=version,
        config_format_version=config_format_version,
        paths=paths,
    )


def _get_section(raw_config: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw_config.get(key, {})
    if not isinstance(value, dict):
        raise ConfigurationError(f"Configuration section '{key}' must be an object.")

    return value


def _get_required_string(
    section: dict[str, Any],
    key: str,
    default: str,
) -> str:
    value = section.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"Configuration value '{key}' must be text.")

    return value.strip()


def _get_int(section: dict[str, Any], key: str, default: int) -> int:
    value = section.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(f"Configuration value '{key}' must be an integer.")

    return value


def _reject_unknown_keys(section: dict[str, Any], allowed_keys: set[str]) -> None:
    unknown_keys = set(section) - allowed_keys
    if unknown_keys:
        joined_keys = ", ".join(sorted(unknown_keys))
        raise ConfigurationError(f"Unknown configuration key: {joined_keys}")
