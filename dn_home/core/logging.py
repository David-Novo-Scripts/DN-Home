"""Console and size-rotated file logging."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from dn_home.core.config import LoggingConfig


def configure_logging(config: LoggingConfig, *, debug: bool = False) -> None:
    """Configure predictable logs without including secrets or message text."""

    level_name = "DEBUG" if debug else config.level
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    config.file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        config.file,
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

