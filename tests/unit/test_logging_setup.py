"""Tests for application logging setup."""

import logging
from logging.handlers import RotatingFileHandler
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from itca_training_centre.utils.logging_setup import (
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    LOGGER_NAME,
    MANAGED_HANDLER_MARKER,
    configure_logging,
    get_application_logger,
    shutdown_logging,
)


class LoggingSetupTests(unittest.TestCase):
    def tearDown(self):
        shutdown_logging()

    def test_configure_logging_creates_log_file(self):
        with TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            try:
                log_file = configure_logging(log_dir)
                logger = get_application_logger()
                logger.info("test message")

                for handler in logger.handlers:
                    handler.flush()

                self.assertTrue(log_file.exists())
                self.assertIn("test message", log_file.read_text(encoding="utf-8"))
            finally:
                shutdown_logging()

    def test_configure_logging_prevents_duplicate_managed_handlers(self):
        with TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            try:
                configure_logging(log_dir)
                configure_logging(log_dir)

                logger = logging.getLogger(LOGGER_NAME)
                managed_handlers = [
                    handler
                    for handler in logger.handlers
                    if getattr(handler, MANAGED_HANDLER_MARKER, False)
                ]

                self.assertEqual(1, len(managed_handlers))
            finally:
                shutdown_logging()

    def test_configure_logging_uses_bounded_rotating_handler(self):
        with TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"

            try:
                configure_logging(log_dir)
                logger = logging.getLogger(LOGGER_NAME)
                managed_handlers = [
                    handler
                    for handler in logger.handlers
                    if getattr(handler, MANAGED_HANDLER_MARKER, False)
                ]

                self.assertIsInstance(managed_handlers[0], RotatingFileHandler)
                self.assertEqual(LOG_MAX_BYTES, managed_handlers[0].maxBytes)
                self.assertEqual(LOG_BACKUP_COUNT, managed_handlers[0].backupCount)
            finally:
                shutdown_logging()


if __name__ == "__main__":
    unittest.main()
