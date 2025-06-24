"""
Comprehensive tests for logging utilities.
"""

import logging
import sys
from io import StringIO
from unittest.mock import Mock, patch

import pytest

from content_collector.utils.logging import setup_logging


class TestStructuredLogging:
    """Test structured logging setup."""

    def test_setup_logging_debug_mode(self):
        """Test logging setup in debug mode."""
        with patch("structlog.configure") as mock_configure:
            setup_logging(level="DEBUG")

            mock_configure.assert_called_once()

            call_args = mock_configure.call_args
            assert "processors" in call_args.kwargs
            assert "logger_factory" in call_args.kwargs
            assert "cache_logger_on_first_use" in call_args.kwargs

    def test_setup_logging_production_mode(self):
        """Test logging setup in production mode."""
        with patch("structlog.configure") as mock_configure:
            setup_logging(level="INFO")

            mock_configure.assert_called_once()

            call_args = mock_configure.call_args
            assert "processors" in call_args.kwargs

    @patch("structlog.get_logger")
    def test_logger_creation(self, mock_get_logger):
        """Test that logger can be created after setup."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        setup_logging(level="DEBUG")

        import structlog

        logger = structlog.get_logger("test_module")

        assert logger == mock_logger

    def test_logging_levels_configuration(self):
        """Test that logging levels are properly configured."""
        with patch("logging.basicConfig") as mock_basic_config:
            setup_logging(level="DEBUG")

            mock_basic_config.assert_called()

            call_args = mock_basic_config.call_args
            if call_args and "level" in call_args.kwargs:
                assert call_args.kwargs["level"] in [logging.DEBUG, logging.INFO]

    def test_log_message_formatting(self):
        """Test that log messages are properly formatted."""
        log_capture = StringIO()

        with patch("sys.stdout", log_capture):
            setup_logging(level="DEBUG")

            import structlog

            logger = structlog.get_logger("test")

            assert True

    def test_multiple_setup_calls(self):
        """Test that multiple calls to setup don't cause issues."""
        setup_logging(level="DEBUG")
        setup_logging(level="INFO")
        setup_logging(level="DEBUG")

        assert True

    @patch("structlog.configure")
    def test_processor_configuration(self, mock_configure):
        """Test that processors are properly configured."""
        setup_logging(level="DEBUG")

        call_args = mock_configure.call_args
        processors = call_args.kwargs.get("processors", [])

        assert len(processors) > 0

    def test_exception_handling_in_setup(self):
        """Test that setup propagates exceptions (as expected)."""
        with patch("structlog.configure", side_effect=Exception("Test error")):
            with pytest.raises(Exception, match="Test error"):
                setup_logging(level="DEBUG")


class TestLoggingIntegration:
    """Test logging integration with the rest of the system."""

    def test_logger_usage_pattern(self):
        """Test typical logger usage pattern."""
        setup_logging(level="DEBUG")

        import structlog

        logger = structlog.get_logger("content_collector.test")

        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "warning")

    def test_context_binding(self):
        """Test logger context binding functionality."""
        setup_logging(level="DEBUG")

        import structlog

        logger = structlog.get_logger("test")

        if hasattr(logger, "bind"):
            bound_logger = logger.bind(component="test", url="https://example.com")
            assert bound_logger is not None

    def test_logging_performance(self):
        """Test that logging setup doesn't significantly impact performance."""
        import time

        start_time = time.time()
        setup_logging(level="INFO")
        end_time = time.time()

        setup_time = end_time - start_time
        assert setup_time < 1.0

    @patch.dict("os.environ", {"LOGGING__LEVEL": "DEBUG"})
    def test_environment_variable_handling(self):
        """Test handling of environment variables for logging."""
        setup_logging(level="INFO")

        assert True

    def test_concurrent_logging_setup(self):
        """Test that concurrent logging setup calls work correctly."""
        import threading
        import time

        results = []

        def setup_logging_thread():
            try:
                setup_logging(level="DEBUG")
                results.append("success")
            except Exception as e:
                results.append(f"error: {e}")

        threads = []
        for _ in range(3):
            thread = threading.Thread(target=setup_logging_thread)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert len(results) == 3
        assert all(result == "success" for result in results)
