from __future__ import annotations

import logging

from app.core.config import Settings

LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s | request_id=%(request_id)s"
)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(RequestContextFilter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
