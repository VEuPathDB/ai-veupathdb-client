"""The WDK answers a site client gives again without a request: a site's
definitions for a time, and the reads of one turn until the turn changes them."""

import asyncio
import copy
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal

from pydantic import JsonValue

from veupathdb.json_types import JSONObject

DEFINITION_SECONDS = 15 * 60
_KEPT_DEFINITIONS = 512

_DEFINITION = re.compile(r"^/record-types/[^/]+(?:/searches/[^/]+)?$")
_SITE_READ = re.compile(
    r"^/record-types/[^/]+/searches/[^/]+"
    r"(?:/refreshed-dependent-params|/reports/standard)?$"
)
_STRATEGY = re.compile(r"^/users/[^/]+/strategies/[^/]+$")
_STEP_REPORT = re.compile(r"^/users/[^/]+/steps/[^/]+/reports/standard$")

type Kept = Literal["definition", "site", "account"]
type Scope = tuple[str, str | None]


def kept_as(method: str, path: str) -> Kept | None:
    match method:
        case "GET" if _DEFINITION.match(path):
            return "definition"
        case "GET" if _STRATEGY.match(path):
            return "account"
        case "POST" if _SITE_READ.match(path):
            return "site"
        case "POST" if _STEP_REPORT.match(path):
            return "account"
        case _:
            return None


def login_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class ReadKey:
    scope: Scope
    method: str
    path: str
    asked: str

    @classmethod
    def of(
        cls,
        scope: Scope,
        method: str,
        path: str,
        params: JSONObject | None,
        body: object,
    ) -> ReadKey:
        asked = json.dumps([params, body], sort_keys=True, default=str)
        return cls(scope, method, path, asked)


@dataclass(frozen=True)
class _Answer:
    value: JsonValue


@dataclass
class Definitions:
    _held: dict[ReadKey, tuple[float, _Answer]] = field(default_factory=dict)

    async def answer(
        self, key: ReadKey, send: Callable[[], Awaitable[JsonValue]]
    ) -> JsonValue:
        now = asyncio.get_running_loop().time()
        held = self._held.get(key)
        if held is not None and now - held[0] < DEFINITION_SECONDS:
            return copy.deepcopy(held[1].value)
        value = await send()
        self._held.pop(key, None)
        if len(self._held) >= _KEPT_DEFINITIONS:
            self._held.pop(next(iter(self._held)))
        self._held[key] = (now, _Answer(copy.deepcopy(value)))
        return value


@dataclass
class TurnReads:
    _held: dict[ReadKey, _Answer] = field(default_factory=dict)
    _account: dict[Scope, set[ReadKey]] = field(default_factory=dict)
    _changes: dict[Scope, int] = field(default_factory=dict)
    _sending: dict[ReadKey, asyncio.Lock] = field(default_factory=dict)

    def forget_the_account(self, scope: Scope) -> None:
        self._changes[scope] = self._changes.get(scope, 0) + 1
        for key in self._account.pop(scope, set()):
            self._held.pop(key, None)

    async def answer(
        self, key: ReadKey, kept: Kept, send: Callable[[], Awaitable[JsonValue]]
    ) -> JsonValue:
        async with self._sending.setdefault(key, asyncio.Lock()):
            held = self._held.get(key)
            if held is not None:
                return copy.deepcopy(held.value)
            changes = self._changes.get(key.scope, 0)
            value = await send()
            if changes == self._changes.get(key.scope, 0):
                self._held[key] = _Answer(copy.deepcopy(value))
                if kept == "account":
                    self._account.setdefault(key.scope, set()).add(key)
            return value


_turn: ContextVar[TurnReads | None] = ContextVar("turn_reads", default=None)


@contextmanager
def turn_reads() -> Iterator[None]:
    if _turn.get() is not None:
        yield
        return
    reset = _turn.set(TurnReads())
    try:
        yield
    finally:
        _turn.reset(reset)


def current_turn_reads() -> TurnReads | None:
    return _turn.get()
