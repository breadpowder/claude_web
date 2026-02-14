"""Logging configuration (TASK-001).

Format: timestamp - level - [module.function] - message
"""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure application logging."""
    log_format = "%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=log_format,
        stream=sys.stdout,
    )


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)
