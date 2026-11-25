"""Inside one turn a site client sends each read once: a strategy and a step report
until the turn writes to the account or reads fresh, and a site read for the turn."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import DataParsingError, WDKError
from veupathdb.wdk import turn_reads
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI

_SERVICE = "https://qa.plasmodb.org/plasmo.qa/service"
_USER = "900000001"
_STRATEGY = 214681950
_STEP = 227385000
_SEARCH = "GenesByInterproDomain"
_CONTEXT_READ = f"POST /record-types/transcript/searches/{_SEARCH}"
_STRATEGY_READ = f"GET /users/{_USER}/strategies/{_STRATEGY}"
_STEP_REPORT = f"POST /users/{_USER}/steps/{_STEP}/reports/standard"


class _Site:
    def __init__(self) -> None:
        self.sent: Counter[str] = Counter()
        self.name = "Genes with a PF00069 domain"
        self.size = 1234
        self.refuse_next: set[str] = set()
        self.garble_next: set[str] = set()
        self.landed = asyncio.Event()
        self.hold_reads = False
        self.write_lands = asyncio.Event()
        self.write_lands.set()

    async def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/plasmo.qa/service")
        if path == "/plasmo.qa/app":
            return httpx.Response(200, text="")
        kind = f"{request.method} {path}"
        self.sent[kind] += 1
        if request.method in {"PUT", "DELETE"} or path.endswith("/steps"):
            return await self._written(request)
        if kind in self.garble_next:
            self.garble_next.discard(kind)
            return httpx.Response(200, json={"strategyId": "not a strategy"})
        if kind in self.refuse_next:
            self.refuse_next.discard(kind)
            return httpx.Response(422, json={"message": "refused"})
        if self.hold_reads and request.method == "GET":
            body = self._strategy()
            await self.landed.wait()
            return httpx.Response(200, json=body)
        return self._answer(request, path)

    async def _written(self, request: httpx.Request) -> httpx.Response:
        await self.write_lands.wait()
        self.size = 7
        if request.method == "POST":
            return httpx.Response(200, json={"id": 9})
        return httpx.Response(204)

    def _answer(self, request: httpx.Request, path: str) -> httpx.Response:
        if request.method == "PATCH":
            self.name = json.loads(request.content)["name"]
            self.landed.set()
            return httpx.Response(204)
        if path.endswith("/reports/standard"):
            return httpx.Response(
                200,
                json={
                    "meta": {"totalCount": self.size, "responseCount": 0},
                    "records": [],
                },
            )
        if path.startswith("/record-types/"):
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "searchData": {"urlSegment": _SEARCH, "paramNames": []},
                    "validation": {"level": "NONE", "isValid": True},
                    "asked": body,
                },
            )
        return httpx.Response(200, json=self._strategy())

    def _strategy(self) -> dict[str, Any]:
        return {
            "strategyId": _STRATEGY,
            "name": self.name,
            "rootStepId": _STEP,
            "recordClassName": "transcript",
            "estimatedSize": self.size,
            "stepTree": {"stepId": _STEP},
            "steps": {
                str(_STEP): {
                    "id": _STEP,
                    "searchName": _SEARCH,
                    "searchConfig": {"parameters": {}},
                    "estimatedSize": self.size,
                }
            },
        }


@contextmanager
def _as(token: str) -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set(token)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


@pytest.fixture
def site() -> _Site:
    return _Site()


@pytest.fixture
def api(site: _Site) -> Iterator[StrategyAPI]:
    client = VEuPathDBClient(
        _SERVICE, site_id="plasmodb", transport=httpx.MockTransport(site.handle)
    )
    with _as("token-of-ada"):
        yield StrategyAPI(client, user_id=_USER)


async def _context_read(api: StrategyAPI, organism: str) -> object:
    return await api.client.get_search_details_with_params(
        "transcript", _SEARCH, {"organism": organism}
    )


async def test_inside_a_turn_a_strategy_is_read_once(
    api: StrategyAPI, site: _Site
) -> None:
    with turn_reads():
        names = [(await api.get_strategy(_STRATEGY)).name for _ in range(5)]

    assert names == ["Genes with a PF00069 domain"] * 5
    assert site.sent[_STRATEGY_READ] == 1


async def test_outside_a_turn_every_read_is_sent(api: StrategyAPI, site: _Site) -> None:
    for _ in range(3):
        await api.get_strategy(_STRATEGY)
        await api.get_step_count(_STEP)
        await _context_read(api, "Plasmodium falciparum 3D7")

    assert (
        site.sent[_STRATEGY_READ],
        site.sent[_STEP_REPORT],
        site.sent[_CONTEXT_READ],
    ) == (3, 3, 3)


async def test_after_a_write_the_turn_reads_what_the_write_made(
    api: StrategyAPI, site: _Site
) -> None:
    with turn_reads():
        before = (await api.get_strategy(_STRATEGY)).name
        await api.get_step_count(_STEP)
        written = await api.update_strategy(_STRATEGY, name="Kinases")
        after = [(await api.get_strategy(_STRATEGY)).name for _ in range(3)]
        await api.get_step_count(_STEP)
        await api.get_step_count(_STEP)

    assert (before, written.name, after) == (
        "Genes with a PF00069 domain",
        "Kinases",
        ["Kinases"] * 3,
    )
    assert (site.sent[_STRATEGY_READ], site.sent[_STEP_REPORT]) == (2, 2)


async def test_a_fresh_read_catches_an_edit_made_on_the_website(
    api: StrategyAPI, site: _Site
) -> None:
    with turn_reads():
        await api.get_strategy(_STRATEGY)
        await api.get_step_count(_STEP)
        site.name = "Renamed on the website"
        site.size = 99
        held = await api.get_strategy(_STRATEGY)
        fresh = await api.get_strategy(_STRATEGY, fresh=True)
        later = await api.get_strategy(_STRATEGY)
        counted = await api.get_step_count(_STEP)

    assert (held.name, fresh.name, later.name, counted) == (
        "Genes with a PF00069 domain",
        "Renamed on the website",
        "Renamed on the website",
        99,
    )
    assert (site.sent[_STRATEGY_READ], site.sent[_STEP_REPORT]) == (2, 2)


async def test_a_search_context_is_read_once_for_each_set_of_values(
    api: StrategyAPI, site: _Site
) -> None:
    with turn_reads():
        for organism in ("Plasmodium falciparum 3D7", "Plasmodium vivax P01") * 4:
            await _context_read(api, organism)

    assert site.sent[_CONTEXT_READ] == 2


async def test_a_site_read_outlives_a_write_to_the_account(
    api: StrategyAPI, site: _Site
) -> None:
    with turn_reads():
        await _context_read(api, "Plasmodium falciparum 3D7")
        await api.update_strategy(_STRATEGY, name="Kinases")
        await _context_read(api, "Plasmodium falciparum 3D7")

    assert site.sent[_CONTEXT_READ] == 1


async def test_reads_sent_at_once_are_sent_once(api: StrategyAPI, site: _Site) -> None:
    with turn_reads():
        answers = await asyncio.gather(
            *(_context_read(api, "Plasmodium falciparum 3D7") for _ in range(4)),
            *(api.get_step_count(_STEP) for _ in range(4)),
        )

    assert answers[4:] == [1234] * 4
    assert (site.sent[_CONTEXT_READ], site.sent[_STEP_REPORT]) == (1, 1)


async def test_a_read_in_flight_when_a_write_lands_is_not_kept(
    api: StrategyAPI, site: _Site
) -> None:
    site.hold_reads = True
    with turn_reads():
        reading = asyncio.create_task(api.get_strategy(_STRATEGY))
        await asyncio.sleep(0)
        await api.client.patch(
            f"/users/{_USER}/strategies/{_STRATEGY}", json={"name": "Kinases"}
        )
        stale = await reading
        site.hold_reads = False
        now = await api.get_strategy(_STRATEGY)

    assert (stale.name, now.name) == ("Genes with a PF00069 domain", "Kinases")
    assert site.sent[_STRATEGY_READ] == 2


async def test_each_login_reads_its_own_strategy(api: StrategyAPI, site: _Site) -> None:
    with turn_reads():
        await api.get_strategy(_STRATEGY)
        with _as("token-of-bea"):
            await api.get_strategy(_STRATEGY)
        await api.get_strategy(_STRATEGY)

    assert site.sent[_STRATEGY_READ] == 2


async def test_a_refused_read_is_not_kept(api: StrategyAPI, site: _Site) -> None:
    site.refuse_next.add(_STRATEGY_READ)
    with turn_reads():
        with pytest.raises(WDKError):
            await api.get_strategy(_STRATEGY)
        await api.get_strategy(_STRATEGY)
        await api.get_strategy(_STRATEGY)

    assert site.sent[_STRATEGY_READ] == 2


async def test_nothing_is_kept_after_the_turn(api: StrategyAPI, site: _Site) -> None:
    with turn_reads():
        await api.get_strategy(_STRATEGY)
    with turn_reads():
        await api.get_strategy(_STRATEGY)
    await api.get_strategy(_STRATEGY)

    assert site.sent[_STRATEGY_READ] == 3


async def test_a_caller_that_changes_its_answer_changes_no_other(
    api: StrategyAPI, site: _Site
) -> None:
    with turn_reads():
        first = await api.get_strategy(_STRATEGY)
        first.steps.clear()
        second = await api.get_strategy(_STRATEGY)

    assert list(second.steps) == [str(_STEP)]
    assert site.sent[_STRATEGY_READ] == 1


_WRITES = [
    ("PUT", f"/users/{_USER}/strategies/{_STRATEGY}/step-tree"),
    ("PUT", f"/users/{_USER}/steps/{_STEP}/search-config"),
    ("DELETE", f"/users/{_USER}/steps/{_STEP}"),
    ("DELETE", f"/users/{_USER}/strategies/{_STRATEGY}"),
    ("POST", f"/users/{_USER}/steps"),
]


async def _write(api: StrategyAPI, method: str, path: str) -> None:
    match method:
        case "PUT":
            await api.client.put(path, json={})
        case "DELETE":
            await api.client.delete(path)
        case _:
            await api.client.post(path, json={})


@pytest.mark.parametrize(("method", "path"), _WRITES)
async def test_a_write_makes_the_next_account_read_go_to_the_site(
    api: StrategyAPI, site: _Site, method: str, path: str
) -> None:
    with turn_reads():
        await api.get_strategy(_STRATEGY)
        await api.get_step_count(_STEP)
        await _write(api, method, path)
        strategy = await api.get_strategy(_STRATEGY)
        counted = await api.get_step_count(_STEP)

    assert (strategy.estimated_size, counted) == (7, 7)
    assert (site.sent[_STRATEGY_READ], site.sent[_STEP_REPORT]) == (2, 2)


async def test_a_held_read_waits_for_a_write_in_flight(
    api: StrategyAPI, site: _Site
) -> None:
    with turn_reads():
        await api.get_strategy(_STRATEGY)
        site.write_lands.clear()
        writing = asyncio.create_task(
            api.client.put(f"/users/{_USER}/strategies/{_STRATEGY}/step-tree", json={})
        )
        await asyncio.sleep(0)
        reading = asyncio.create_task(api.get_strategy(_STRATEGY))
        await asyncio.sleep(0)
        waited = not reading.done()
        site.write_lands.set()
        await writing
        read = await reading

    assert (waited, read.estimated_size) == (True, 7)
    assert site.sent[_STRATEGY_READ] == 2


async def test_an_unreadable_strategy_is_not_kept(
    api: StrategyAPI, site: _Site
) -> None:
    site.garble_next.add(_STRATEGY_READ)
    with turn_reads():
        with pytest.raises(DataParsingError):
            await api.get_strategy(_STRATEGY)
        names = [(await api.get_strategy(_STRATEGY)).name for _ in range(2)]

    assert names == ["Genes with a PF00069 domain"] * 2
    assert site.sent[_STRATEGY_READ] == 2
