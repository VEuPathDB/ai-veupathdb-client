"""The WDK answers a site client gives again without a request: a site's
definitions for a time, and the reads of one turn until the turn changes them."""

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal

import pydantic
from pydantic import JsonValue, TypeAdapter

from veupathdb.json_types import JSONObject
from veupathdb.wdk.wdk_models import (
    WDKAnswer,
    WDKRecordType,
    WDKSearchResponse,
    WDKStrategyDetails,
)
from veupathdb.wdk.wdk_parameters import WDKParameter

DEFINITION_SECONDS = 15 * 60
DEFINITION_BYTES = 32 * 1024 * 1024

_RECORD_TYPE = re.compile(r"^/record-types/[^/]+$")
_SEARCH = re.compile(r"^/record-types/[^/]+/searches/[^/]+$")
_REFRESH = re.compile(
    r"^/record-types/[^/]+/searches/[^/]+/refreshed-dependent-params$"
)
_SEARCH_REPORT = re.compile(r"^/record-types/[^/]+/searches/[^/]+/reports/standard$")
_STRATEGY = re.compile(r"^/users/[^/]+/strategies/[^/]+$")
_STEP_REPORT = re.compile(r"^/users/[^/]+/steps/[^/]+/reports/standard$")

type Kept = Literal["definition", "site", "account"]
type Scope = tuple[str, str | None]


@dataclass(frozen=True)
class HeldRead:
    kept: Kept
    answer: TypeAdapter[object]

    def readable(self, value: JsonValue) -> bool:
        if value is None:
            return False
        try:
            self.answer.validate_python(value)
        except pydantic.ValidationError:
            return False
        return True


_HELD: tuple[tuple[str, re.Pattern[str], HeldRead], ...] = (
    ("GET", _RECORD_TYPE, HeldRead("definition", TypeAdapter(WDKRecordType))),
    ("GET", _SEARCH, HeldRead("definition", TypeAdapter(WDKSearchResponse))),
    ("GET", _STRATEGY, HeldRead("account", TypeAdapter(WDKStrategyDetails))),
    ("POST", _SEARCH, HeldRead("site", TypeAdapter(WDKSearchResponse))),
    ("POST", _REFRESH, HeldRead("site", TypeAdapter(list[WDKParameter]))),
    ("POST", _SEARCH_REPORT, HeldRead("site", TypeAdapter(WDKAnswer))),
    ("POST", _STEP_REPORT, HeldRead("account", TypeAdapter(WDKAnswer))),
)


def held_read(method: str, path: str) -> HeldRead | None:
    return next(
        (read for verb, shape, read in _HELD if verb == method and shape.match(path)),
        None,
    )


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


def _kept(value: JsonValue) -> str:
    return json.dumps(value)


def _given(kept: str) -> JsonValue:
    answer: JsonValue = json.loads(kept)
    return answer


@dataclass
class Definitions:
    _held: dict[ReadKey, tuple[float, str]] = field(default_factory=dict)
    _bytes: int = 0

    async def answer(
        self, key: ReadKey, read: HeldRead, send: Callable[[], Awaitable[JsonValue]]
    ) -> JsonValue:
        now = asyncio.get_running_loop().time()
        held = self._held.get(key)
        if held is not None and now - held[0] < DEFINITION_SECONDS:
            return _given(held[1])
        value = await send()
        self._drop(key)
        if read.readable(value):
            self._keep(key, now, _kept(value))
        return value

    def _drop(self, key: ReadKey) -> None:
        held = self._held.pop(key, None)
        if held is not None:
            self._bytes -= len(held[1])

    def _keep(self, key: ReadKey, now: float, text: str) -> None:
        if len(text) > DEFINITION_BYTES:
            return
        for older, (read_at, _) in list(self._held.items()):
            fresh = now - read_at < DEFINITION_SECONDS
            if fresh and self._bytes + len(text) <= DEFINITION_BYTES:
                break
            self._drop(older)
        self._held[key] = (now, text)
        self._bytes += len(text)


@dataclass
class TurnReads:
    _held: dict[ReadKey, str] = field(default_factory=dict)
    _account: dict[Scope, set[ReadKey]] = field(default_factory=dict)
    _changes: dict[Scope, int] = field(default_factory=dict)
    _sending: dict[ReadKey, asyncio.Lock] = field(default_factory=dict)
    _writing: dict[Scope, int] = field(default_factory=dict)
    _settled: dict[Scope, asyncio.Event] = field(default_factory=dict)

    def forget_the_account(self, scope: Scope) -> None:
        self._changes[scope] = self._changes.get(scope, 0) + 1
        for key in self._account.pop(scope, set()):
            self._held.pop(key, None)

    @asynccontextmanager
    async def writing(self, scope: Scope) -> AsyncIterator[None]:
        self._writing[scope] = self._writing.get(scope, 0) + 1
        self._settled.setdefault(scope, asyncio.Event()).clear()
        try:
            yield
        finally:
            self.forget_the_account(scope)
            self._writing[scope] -= 1
            if self._writing[scope] == 0:
                self._settled[scope].set()

    async def answer(
        self, key: ReadKey, read: HeldRead, send: Callable[[], Awaitable[JsonValue]]
    ) -> JsonValue:
        if read.kept == "account":
            while self._writing.get(key.scope, 0):
                await self._settled[key.scope].wait()
        async with self._sending.setdefault(key, asyncio.Lock()):
            held = self._held.get(key)
            if held is not None:
                return _given(held)
            changes = self._changes.get(key.scope, 0)
            value = await send()
            if changes == self._changes.get(key.scope, 0) and read.readable(value):
                self._held[key] = _kept(value)
                if read.kept == "account":
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
