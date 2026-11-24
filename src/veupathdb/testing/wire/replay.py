from __future__ import annotations

import json
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from veupathdb.json_types import JSONValue
from veupathdb.testing.wire.key import canonical_body
from veupathdb.testing.wire.models import Cassette, Exchange

MissReason = Literal["unrecorded", "used-up", "host", "no-cassette"]


class Miss(BaseModel):
    model_config = ConfigDict(frozen=True)

    cassette: str
    method: str
    host: str
    path: str
    reason: MissReason
    body: str | None = None
    nearest: str = ""
    differences: list[str] = Field(default_factory=list)


class Played:
    def __init__(self, cassette: Cassette) -> None:
        self.cassette = cassette
        self._writes: dict[str, list[Exchange]] = defaultdict(list)
        self._reads: dict[str, list[Exchange]] = defaultdict(list)
        for exchange in sorted(cassette.exchanges, key=lambda e: e.seq):
            held = self._writes if exchange.is_write() else self._reads
            held[exchange.key()].append(exchange)
        self.epoch = 0
        self._written: dict[str, int] = {}
        self._read: dict[tuple[str, int], int] = {}

    def rewind(self) -> None:
        self.epoch = 0
        self._written = {}
        self._read = {}

    def take(self, key: str, *, write: bool) -> Exchange | None:
        if write:
            return self._take_write(key)
        return self._take_read(key)

    def _take_write(self, key: str) -> Exchange | None:
        queue = self._writes.get(key, [])
        sent = self._written.get(key, 0)
        if sent >= len(queue):
            return None
        self._written[key] = sent + 1
        self.epoch += 1
        return queue[sent]

    def _take_read(self, key: str) -> Exchange | None:
        recorded = self._reads.get(key, [])
        at_epoch = [e for e in recorded if e.epoch == self.epoch]
        if at_epoch:
            taken = self._read.get((key, self.epoch), 0)
            self._read[key, self.epoch] = taken + 1
            return at_epoch[min(taken, len(at_epoch) - 1)]
        before = [e for e in recorded if e.epoch < self.epoch]
        return before[-1] if before else None

    def unsent_writes(self) -> list[Exchange]:
        return sorted(
            (
                exchange
                for key, queue in self._writes.items()
                for exchange in queue[self._written.get(key, 0) :]
            ),
            key=lambda e: e.seq,
        )


def _parsed(body: bytes) -> JSONValue:
    text = canonical_body(body)
    try:
        parsed: JSONValue = json.loads(text) if text else None
    except ValueError:
        return text
    return parsed


def _differences(recorded: JSONValue, sent: JSONValue, at: str = "$") -> list[str]:
    match recorded, sent:
        case dict(), dict():
            return [
                difference
                for name in sorted(recorded.keys() | sent.keys())
                for difference in _differences(
                    recorded.get(name), sent.get(name), f"{at}.{name}"
                )
            ]
        case list(), list() if len(recorded) == len(sent):
            return [
                difference
                for index, (old, new) in enumerate(zip(recorded, sent, strict=True))
                for difference in _differences(old, new, f"{at}[{index}]")
            ]
        case _ if recorded == sent:
            return []
        case _:
            return [f"{at}: {json.dumps(recorded)} -> {json.dumps(sent)}"]


def nearest_difference(
    cassette: Cassette, method: str, host: str, path: str, body: bytes
) -> tuple[str, list[str]]:
    sent = _parsed(body)
    candidates = [
        _differences(_parsed(exchange.request_bytes()), sent)
        for exchange in cassette.exchanges
        if (exchange.method, exchange.host, exchange.path) == (method, host, path)
    ]
    if not candidates:
        return "", []
    return f"{method} {host} {path}", min(candidates, key=len)


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def render_misses(cassette: str, misses: list[Miss], unsent: list[Exchange]) -> str:
    parts = []
    if misses:
        parts.append(
            _count(
                len(misses), "request has no recording", "requests have no recording"
            )
        )
    if unsent:
        parts.append(
            _count(
                len(unsent),
                "recorded write was not sent",
                "recorded writes were not sent",
            )
        )
    lines = [f"WDK replay: {', '.join(parts)} ({cassette})."]
    for miss in misses:
        lines.append(f"  {miss.method} {miss.host} {miss.path}")
        if miss.reason != "unrecorded":
            lines.append(f"    {miss.reason}")
        lines.extend(
            f"    nearest recording differs at {difference}"
            for difference in miss.differences[:5]
        )
    lines.extend(
        f"  recorded but not sent: {e.method} {e.host} {e.path}" for e in unsent
    )
    return "\n".join(lines)
