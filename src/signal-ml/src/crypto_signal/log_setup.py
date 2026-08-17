from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from .config import LoggingConfig


LOGGER_NAMESPACE = "crypto_signal"


def get_logger(module_name: str) -> logging.Logger:
    """Return a child logger inside the project's shared logging namespace."""
    short_name = module_name.rsplit(".", 1)[-1]
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{short_name}")


def configure_logging(config: LoggingConfig) -> logging.Logger:
    """Configure readable console logs and a size-limited rotating log file."""
    logger = logging.getLogger(LOGGER_NAMESPACE)
    logger.setLevel(getattr(logging, config.level))
    logger.propagate = False

    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(getattr(logging, config.level))
    console.setFormatter(formatter)
    logger.addHandler(console)

    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        config.log_file,
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, config.level))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info(
        "Logging ready | level=%s | file=%s | rotation=%s bytes x %s backups",
        config.level,
        config.log_file,
        f"{config.max_bytes:,}",
        config.backup_count,
    )
    return logger

