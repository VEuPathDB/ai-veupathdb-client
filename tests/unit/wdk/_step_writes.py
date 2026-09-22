"""Test doubles shared by the step write and step report tests."""

from __future__ import annotations

from typing import Any


class Recorder:
    """Captures a request body instead of reaching WDK, and answers ``reply``."""

    def __init__(self, reply: Any = None) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.reply = reply

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> Any:
        del path
        self.bodies.append(json or {})
        return self.reply

    @property
    def body(self) -> dict[str, Any]:
        return self.bodies[-1]


async def no_expansion(
    record_type: str, search_name: str, params: dict[str, str]
) -> dict[str, str]:
    """Stands in for the tree-param expansion, which reads the catalog."""
    del record_type, search_name
    return params
