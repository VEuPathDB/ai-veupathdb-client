import re
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from pydantic import BaseModel, ConfigDict

_ON_A_STRATEGY = re.compile(r"^/users/[^/]+/strategies/(\d+)(?:/|$)")


class StrategyRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    site_id: str
    strategy_id: int


type StrategyGate = Callable[[StrategyRequest], AbstractAsyncContextManager[None]]


@asynccontextmanager
async def open_strategy_gate(_request: StrategyRequest) -> AsyncIterator[None]:
    yield


class _GateSlot:
    def __init__(self) -> None:
        self.gate: StrategyGate = open_strategy_gate


_slot = _GateSlot()


def use_strategy_gate(gate: StrategyGate) -> None:
    _slot.gate = gate


def strategy_gate() -> StrategyGate:
    return _slot.gate


def strategy_request(site_id: str, path: str) -> StrategyRequest | None:
    on_a_strategy = _ON_A_STRATEGY.match(path)
    if on_a_strategy is None:
        return None
    return StrategyRequest(site_id=site_id, strategy_id=int(on_a_strategy.group(1)))


@asynccontextmanager
async def in_strategy_line(site_id: str, path: str) -> AsyncIterator[None]:
    request = strategy_request(site_id, path)
    if request is None:
        yield
        return
    async with _slot.gate(request):
        yield


__all__ = [
    "StrategyGate",
    "StrategyRequest",
    "open_strategy_gate",
    "strategy_gate",
    "use_strategy_gate",
]
