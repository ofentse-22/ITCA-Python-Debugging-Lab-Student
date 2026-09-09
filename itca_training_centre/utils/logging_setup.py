"""Centralized logging setup."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .exceptions import LoggingSetupError


LOGGER_NAME = "itca_training_centre"
LOG_FILE_NAME = "application.log"
MANAGED_HANDLER_MARKER = "_itca_training_centre_managed"
LOG_MAX_BYTES = 1_048_576
LOG_BACKUP_COUNT = 3


def configure_logging(log_dir: Path, level: int = logging.INFO) -> Path:
    """Configure the application logger and return the log file path."""
    log_directory = Path(log_dir)
    log_file = log_directory / LOG_FILE_NAME

    try:
        log_directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as error:
        logging.getLogger(LOGGER_NAME).error("Logging setup failed")
        raise LoggingSetupError(f"Could not initialize log file: {log_file}") from error

    setattr(handler, MANAGED_HANDLER_MARKER, True)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )

    logger = get_application_logger()
    logger.setLevel(level)
    logger.propagate = False
    _remove_managed_handlers(logger)
    logger.addHandler(handler)

    return log_file


def get_application_logger() -> logging.Logger:
    """Return the application logger."""
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    return logger


def shutdown_logging() -> None:
    """Close managed application log handlers."""
    _remove_managed_handlers(get_application_logger())


def _remove_managed_handlers(logger: logging.Logger) -> None:
    for existing_handler in list(logger.handlers):
        if getattr(existing_handler, MANAGED_HANDLER_MARKER, False):
            logger.removeHandler(existing_handler)
            existing_handler.close()
