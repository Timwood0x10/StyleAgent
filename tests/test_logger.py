"""
Tests for logger module
"""

import logging
import pytest
from src.utils.logger import get_logger, Logger


class TestLogger:
    """Test logger module"""

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a logger instance"""
        logger = get_logger("test_module")
        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_get_logger_has_name(self):
        """Test that logger has correct name"""
        logger = get_logger("test_module")
        assert logger.name == "test_module"

    def test_logger_has_handlers(self):
        """Test that logger has handlers configured"""
        logger = get_logger("test_handler")
        assert len(logger.handlers) > 0

    def test_logger_can_log(self):
        """Test that logger can log messages"""
        logger = get_logger("test_log")
        # Should not raise any exceptions
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

    def test_logger_class_get_logger(self):
        """Test Logger class get_logger method"""
        logger = Logger.get_logger("test_class")
        assert logger is not None
        assert isinstance(logger, logging.Logger)
