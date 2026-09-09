"""Application startup and shutdown orchestration."""

from collections.abc import Callable
from pathlib import Path

from .cli.main_menu import run_main_menu
from .config.settings import ensure_runtime_directories, load_config
from .data.migrations import initialize_database
from .utils.exceptions import (
    ConfigurationError,
    DatabaseError,
    LoggingSetupError,
    PathSafetyError,
)
from .utils.logging_setup import (
    configure_logging,
    get_application_logger,
    shutdown_logging,
)


InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]


def main(
    input_func: InputFunction = input,
    output_func: OutputFunction = print,
    project_root: Path | None = None,
) -> int
    """Start the application and return a process-style exit code."""
    try:
        config = load_config(project_root=project_root)
        ensure_runtime_directories(config)
    except (ConfigurationError, PathSafetyError, OSError) as error:
        output_func(f"Startup failed: {error}")
        return 2

    try:
        configure_logging(config.paths.log_dir)
    except LoggingSetupError as error:
        output_func(f"Logging could not be initialized: {error}")
        return 3

    logger = get_application_logger()
    logger.info("Application startup")

    try:
        database_status = initialize_database(config.paths.database_path)
    except DatabaseError as error:
        logger.exception("Database initialization failed")
        output_func(f"Database initialization failed: {error}")
        shutdown_logging()
        return 4

    try:
        try:
            return run_main_mneu(
                config=config,
                database_status=database_status,
                input_func=input_func,
                output_func=output_func,
            )
        except KeyboardInterrupt:
            output_func("")
            output_func("Application interrupted. Exiting.")
            return 130
    finally:
        logger.info("Application shutdown")
        shutdown_logging()
