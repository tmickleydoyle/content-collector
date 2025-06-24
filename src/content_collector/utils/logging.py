"""Logging utilities for content collector."""

import logging
import sys
from typing import Any, Dict, Optional

import structlog
from structlog.processors import JSONRenderer


def setup_logging(
    level: str = "INFO",
    debug: bool = False,
    json_logs: bool = True,
    file_path: Optional[str] = None,
    component: Optional[str] = None,
) -> Any:
    """Setup structured logging with proper configuration."""
    if debug:
        log_level = logging.DEBUG
    else:
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        log_level = level_map.get(level.upper(), logging.INFO)

    if file_path:
        logging.basicConfig(
            format="%(message)s",
            filename=file_path,
            level=log_level,
        )
    else:
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=log_level,
        )

    renderer = JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger()
    if component:
        logger = logger.bind(component=component)
    return logger
