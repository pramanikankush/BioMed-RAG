import sys
import logging
import json
from contextvars import ContextVar
from typing import Any

# Context variable to hold request IDs across asynchronous coroutine scopes
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

class StructuredJSONFormatter(logging.Formatter):
    """
    Format logs as structured JSON records for production observability.
    Includes request ID if available in context.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get() or None
        }

        # Include exception traceback if logged
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Merge standard logging extra dictionary attributes if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)  # type: ignore

        return json.dumps(log_data)

def get_logger(name: str) -> logging.Logger:
    """
    Returns a structured logger configured to output JSON to standard output.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid adding multiple handlers if already initialized
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger
