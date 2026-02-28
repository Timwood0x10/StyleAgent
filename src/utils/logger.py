"""
Logging Module - Structured logging with configuration
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .config import config


class Logger:
    """Logger wrapper with configuration"""

    _loggers: dict = {}

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get or create logger by name"""
        if name in cls._loggers:
            return cls._loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, config.LOG_LEVEL))

        # Avoid duplicate handlers
        if not logger.handlers:
            cls._setup_handler(logger)

        cls._loggers[name] = logger
        return logger

    @classmethod
    def _setup_handler(cls, logger: logging.Logger):
        """Setup log handlers (console + file)"""
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, config.LOG_LEVEL))
        console_formatter = logging.Formatter(config.LOG_FORMAT)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # File handler (optional)
        log_file = config.LOG_FILE
        if log_file:
            # Create log directory if not exists
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=config.LOG_MAX_BYTES,
                backupCount=config.LOG_BACKUP_COUNT
            )
            file_handler.setLevel(getattr(logging, config.LOG_LEVEL))
            file_formatter = logging.Formatter(config.LOG_FORMAT)
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)


# Convenience function
def get_logger(name: str) -> logging.Logger:
    """Get logger instance"""
    return Logger.get_logger(name)
