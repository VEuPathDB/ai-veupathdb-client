from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import httpx
import pytest

from veupathdb.wdk import (
    StrategyAPI,
    StrategyRequest,
    VEuPathDBClient,
    WDKStepTree,
    strategy_gate,
    use_strategy_gate,
)

_STRATEGY = 214644620
_HELD = {
    "strategyId": _STRATEGY,
    "name": "kinases",
    "rootStepId": 227283440,
    "stepTree": {"stepId": 227283440},
    "steps": {},
    "recordClassName": "transcript",
}


class _Site(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.in_flight = 0
        self.most_in_flight = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/app"):
            return httpx.Response(200, text="ok")
        path = request.url.path.removeprefix("/service")
        self.sent.append((request.method, path))
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        self.entered.set()
        await self.release.wait()
        self.in_flight -= 1
        if request.method == "GET" and path.endswith(f"/strategies/{_STRATEGY}"):
            return httpx.Response(200, json=_HELD)
        if request.method == "GET" and path.endswith("/strategies"):
            return httpx.Response(200, json=[])
        return httpx.Response(204)


async def _client(site: _Site) -> VEuPathDBClient:
    client = VEuPathDBClient(
        base_url="https://plasmodb.invalid/service", site_id="plasmodb"
    )
    async with client._client_lock:
        client._client = httpx.AsyncClient(
            base_url=client.base_url, transport=site, follow_redirects=True
        )
    return client


@pytest.fixture
def gate_calls() -> Iterator[list[StrategyRequest]]:
    calls: list[StrategyRequest] = []
    previous = strategy_gate()

    @asynccontextmanager
    async def recording(request: StrategyRequest) -> AsyncIterator[None]:
        calls.append(request)
        yield

    use_strategy_gate(recording)
    try:
        yield calls
    finally:
        use_strategy_gate(previous)


@pytest.fixture
def one_at_a_time() -> Iterator[None]:
    previous = strategy_gate()
    locks: dict[StrategyRequest, asyncio.Lock] = {}

    @asynccontextmanager
    async def line(request: StrategyRequest) -> AsyncIterator[None]:
        async with locks.setdefault(request, asyncio.Lock()):
            yield

    use_strategy_gate(line)
    try:
        yield
    finally:
        use_strategy_gate(previous)


_ON_THE_STRATEGY = [
    ("GET", f"/users/1/strategies/{_STRATEGY}"),
    ("PATCH", f"/users/1/strategies/{_STRATEGY}"),
    ("DELETE", f"/users/1/strategies/{_STRATEGY}"),
    ("PUT", f"/users/1/strategies/{_STRATEGY}/step-tree"),
    ("POST", f"/users/1/strategies/{_STRATEGY}/duplicated-step-tree"),
    ("GET", f"/users/current/strategies/{_STRATEGY}"),
]


@pytest.mark.usefixtures("wdk_request_token")
class TestEveryRequestOnAStrategyPassesTheGate:
    @pytest.mark.parametrize(("method", "path"), _ON_THE_STRATEGY)
    async def test_the_gate_names_the_site_and_the_strategy(
        self, gate_calls: list[StrategyRequest], method: str, path: str
    ) -> None:
        client = await _client(_Site())

        await client._request(method, path, json={} if method != "GET" else None)

        assert gate_calls == [
            StrategyRequest(site_id="plasmodb", strategy_id=_STRATEGY)
        ]

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/users/1/strategies"),
            ("POST", "/users/1/strategies"),
            ("GET", "/users/1/steps/227283440"),
            ("POST", "/users/1/steps/227283440/reports/standard"),
        ],
    )
    async def test_a_request_on_no_one_strategy_passes_no_gate(
        self, gate_calls: list[StrategyRequest], method: str, path: str
    ) -> None:
        client = await _client(_Site())

        await client._request(method, path, json={} if method != "GET" else None)

        assert gate_calls == []

    async def test_an_update_sends_each_of_its_requests_through_the_gate(
        self, gate_calls: list[StrategyRequest]
    ) -> None:
        site = _Site()
        api = StrategyAPI(await _client(site), user_id="1")

        await api.update_strategy(
            _STRATEGY, step_tree=WDKStepTree(step_id=227283440), name="kinases"
        )

        assert [method for method, _ in site.sent] == ["PUT", "PATCH", "GET"]
        assert len(gate_calls) == 3


@pytest.mark.usefixtures("wdk_request_token")
async def test_without_a_gate_a_strategy_read_is_sent() -> None:
    site = _Site()
    api = StrategyAPI(await _client(site), user_id="1")

    held = await api.get_strategy(_STRATEGY)

    assert held.root_step_id == 227283440


@pytest.mark.usefixtures("wdk_request_token", "one_at_a_time")
async def test_a_read_waits_while_a_tree_write_on_its_strategy_is_in_flight() -> None:
    site = _Site()
    site.release.clear()
    api = StrategyAPI(await _client(site), user_id="1")
    write = asyncio.create_task(
        api.update_strategy(_STRATEGY, step_tree=WDKStepTree(step_id=227283440))
    )
    await site.entered.wait()
    read = asyncio.create_task(api.get_strategy(_STRATEGY))
    for _ in range(20):
        await asyncio.sleep(0)
    sent_during_the_write = list(site.sent)

    site.release.set()
    await asyncio.gather(write, read)

    assert sent_during_the_write == [
        ("PUT", f"/users/1/strategies/{_STRATEGY}/step-tree")
    ]
    assert site.most_in_flight == 1
