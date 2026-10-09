import asyncio
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import (
    AbstractAsyncContextManager,
    asynccontextmanager,
    contextmanager,
)
from contextvars import ContextVar
from typing import Literal

from pydantic import BaseModel, ConfigDict

from veupathdb.observer import get_observer

type SearchKind = Literal["report", "step", "strategy", "analysis"]
type SearchLine = Literal["turn", "site"]

HIGH_SPEED_SNP_SEARCHES: frozenset[str] = frozenset(
    {
        "GenesByNgsSnps",
        "NgsSnpsByGeneIds",
        "NgsSnpsByIsolateGroup",
        "NgsSnpsByLocation",
        "NgsSnpsByTwoIsolateGroups",
        "NgsSnpsByTwoIsolateGroupsWiz",
        "SnpsByGeneId",
        "SnpsByIsolatePattern",
        "SnpsByStrain",
        "VariantsByGeneIds",
        "VariantsByIsolateGroup",
        "VariantsByLocation",
        "VariantsByTwoIsolateGroups",
    }
)


class SearchRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    site_id: str
    kind: SearchKind
    search_names: frozenset[str] = frozenset()


type SearchGate = Callable[[SearchRequest], AbstractAsyncContextManager[None]]


def runs_an_expensive_search(request: SearchRequest) -> bool:
    return not request.search_names.isdisjoint(HIGH_SPEED_SNP_SEARCHES)


@asynccontextmanager
async def open_search_gate(_request: SearchRequest) -> AsyncIterator[None]:
    yield


class _GateSlot:
    def __init__(self) -> None:
        self.gate: SearchGate = open_search_gate


_slot = _GateSlot()


def use_search_gate(gate: SearchGate) -> None:
    _slot.gate = gate


def search_gate() -> SearchGate:
    return _slot.gate


class SearchTurn:
    def __init__(self) -> None:
        self._lines: dict[str, asyncio.Lock] = {}

    def line(self, site_id: str) -> asyncio.Lock:
        held = self._lines.get(site_id)
        if held is None:
            held = asyncio.Lock()
            self._lines[site_id] = held
        return held


_turn: ContextVar[SearchTurn | None] = ContextVar("veupathdb_search_turn", default=None)


@contextmanager
def search_turn() -> Iterator[SearchTurn]:
    turn = SearchTurn()
    reset = _turn.set(turn)
    try:
        yield turn
    finally:
        _turn.reset(reset)


@asynccontextmanager
async def waited_for(
    site_id: str, line: SearchLine, held: AbstractAsyncContextManager[object]
) -> AsyncIterator[None]:
    start = time.monotonic()
    async with held:
        get_observer().on_wdk_search_wait(
            time.monotonic() - start, {"site": site_id, "line": line}
        )
        yield


@asynccontextmanager
async def in_turn_line(site_id: str) -> AsyncIterator[None]:
    turn = _turn.get()
    if turn is None:
        yield
        return
    async with waited_for(site_id, "turn", turn.line(site_id)):
        yield


__all__ = [
    "HIGH_SPEED_SNP_SEARCHES",
    "SearchGate",
    "SearchKind",
    "SearchLine",
    "SearchRequest",
    "SearchTurn",
    "open_search_gate",
    "runs_an_expensive_search",
    "search_gate",
    "search_turn",
    "use_search_gate",
]
