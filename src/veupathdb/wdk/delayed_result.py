"""Recognises WDK's delayed-result sentinel, which arrives as a success."""

from __future__ import annotations

from pydantic import JsonValue

DELAYED_RESULT_MESSAGE = "WDK-DELAYED-RESULT"


class WDKDelayedResultError(Exception):
    """WDK is still computing the result. Temporary, so it is retried."""

    def __init__(self) -> None:
        super().__init__(f"WDK returned {DELAYED_RESULT_MESSAGE}; result not ready")


def is_delayed_result(body: JsonValue) -> bool:
    """Whether a body is the delay sentinel. Checked by shape; the status is 2xx."""
    return isinstance(body, dict) and body.get("message") == DELAYED_RESULT_MESSAGE
