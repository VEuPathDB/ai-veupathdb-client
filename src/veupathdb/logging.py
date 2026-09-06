"""The logger the library binds. The host owns every processor and handler."""

from typing import cast

import structlog


def get_logger(name: str) -> structlog.BoundLogger:
    """A bound logger under this name."""
    return cast("structlog.BoundLogger", structlog.get_logger(name))
