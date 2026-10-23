"""Inside one scope a site client reads each search definition once, under the
login that asked, and keeps nothing after the scope ends."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
import respx

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import DataParsingError
from veupathdb.json_types import JSONObject
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import search_definitions_read_once
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import NewStepSpec, WDKSearchConfig

pytestmark = pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_molecular_weight.json"),
    reason=NEEDS_QA_RECORDING,
)

_SERVICE = "https://qa.plasmodb.org/plasmo.qa/service"
_WEBAPP = "https://qa.plasmodb.org/plasmo.qa/app"
_TOXO = "https://qa.toxodb.org/toxo.qa/service"
_SEARCH = "GenesByMolecularWeight"
_DEFINITION = f"{_SERVICE}/record-types/transcript/searches/{_SEARCH}"
_PARAMS = {
    "organism": '["Plasmodium"]',
    "min_molecular_weight": "10000",
    "max_molecular_weight": "20000",
}


def _recorded() -> JSONObject:
    body = load_recorded("search_genes_by_molecular_weight").json_body()
    assert isinstance(body, dict)
    return body


def _shown_to(login: str) -> JSONObject:
    body = copy.deepcopy(_recorded())
    search = body["searchData"]
    assert isinstance(search, dict)
    search["displayName"] = f"seen by {login}"
    return body


def _per_login(request: httpx.Request) -> httpx.Response:
    cookie = request.headers.get("cookie", "")
    login = next(t for t in ("ada", "bea") if f"Authorization=token-of-{t}" in cookie)
    return httpx.Response(200, json=_shown_to(login))


@contextmanager
def _as(token: str) -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set(token)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


@pytest.fixture
def site() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(_WEBAPP).mock(return_value=httpx.Response(200, text=""))
        router.get("https://qa.toxodb.org/toxo.qa/app").mock(
            return_value=httpx.Response(200, text="")
        )
        yield router


@pytest.fixture
def ada() -> Iterator[None]:
    with _as("token-of-ada"):
        yield


async def _read(client: VEuPathDBClient, *, expand: bool = True) -> str:
    details = await client.get_search_details(
        "transcript", _SEARCH, expand_params=expand
    )
    return details.search_data.display_name


async def test_a_definition_is_read_once_inside_a_scope(
    site: respx.MockRouter, ada: None
) -> None:
    read = site.get(_DEFINITION).mock(side_effect=_per_login)
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    with search_definitions_read_once():
        first = await _read(client)
        second = await _read(client)

    assert (first, second, read.call_count) == ("seen by ada", "seen by ada", 1)


async def test_outside_a_scope_every_call_reads(
    site: respx.MockRouter, ada: None
) -> None:
    read = site.get(_DEFINITION).mock(side_effect=_per_login)
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    await _read(client)
    await _read(client)

    assert read.call_count == 2


async def test_nothing_is_kept_after_the_scope_ends(
    site: respx.MockRouter, ada: None
) -> None:
    read = site.get(_DEFINITION).mock(side_effect=_per_login)
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    with search_definitions_read_once():
        await _read(client)
    with search_definitions_read_once():
        await _read(client)
    await _read(client)

    assert read.call_count == 3


async def test_the_plain_and_the_expanded_definition_are_kept_apart(
    site: respx.MockRouter, ada: None
) -> None:
    read = site.get(_DEFINITION).mock(side_effect=_per_login)
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    with search_definitions_read_once():
        await _read(client, expand=True)
        await _read(client, expand=False)
        await _read(client, expand=True)
        await _read(client, expand=False)

    assert [call.request.url.params.get("expandParams") for call in read.calls] == [
        "true",
        None,
    ]


async def test_each_site_reads_its_own_definition(
    site: respx.MockRouter, ada: None
) -> None:
    plasmo = site.get(_DEFINITION).mock(side_effect=_per_login)
    toxo = site.get(f"{_TOXO}/record-types/transcript/searches/{_SEARCH}").mock(
        return_value=httpx.Response(200, json=_shown_to("toxodb"))
    )

    with search_definitions_read_once():
        here = await _read(VEuPathDBClient(_SERVICE, site_id="plasmodb"))
        there = await _read(VEuPathDBClient(_TOXO, site_id="toxodb"))

    assert (here, there) == ("seen by ada", "seen by toxodb")
    assert (plasmo.call_count, toxo.call_count) == (1, 1)


async def test_a_second_login_in_one_scope_reads_its_own_definition(
    site: respx.MockRouter,
) -> None:
    read = site.get(_DEFINITION).mock(side_effect=_per_login)
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    with search_definitions_read_once():
        with _as("token-of-ada"):
            ada = await _read(client)
        with _as("token-of-bea"):
            bea = await _read(client)
        with _as("token-of-ada"):
            ada_again = await _read(client)

    assert (ada, bea, ada_again) == ("seen by ada", "seen by bea", "seen by ada")
    assert read.call_count == 2


async def test_two_saves_at_once_never_see_each_other_s_definition(
    site: respx.MockRouter,
) -> None:
    both_read = asyncio.Barrier(2)
    read = site.get(_DEFINITION).mock(side_effect=_per_login)
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    async def save(token: str) -> list[str]:
        seen: list[str] = []
        with _as(token), search_definitions_read_once():
            seen.append(await _read(client))
            await both_read.wait()
            seen.append(await _read(client))
        return seen

    ada, bea = await asyncio.gather(save("token-of-ada"), save("token-of-bea"))

    assert ada == ["seen by ada", "seen by ada"]
    assert bea == ["seen by bea", "seen by bea"]
    assert read.call_count == 2


async def test_a_scope_inside_a_scope_keeps_the_outer_reads(
    site: respx.MockRouter, ada: None
) -> None:
    read = site.get(_DEFINITION).mock(side_effect=_per_login)
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    with search_definitions_read_once():
        await _read(client)
        with search_definitions_read_once():
            await _read(client)
        await _read(client)

    assert read.call_count == 1


async def test_an_unreadable_definition_is_not_kept(
    site: respx.MockRouter, ada: None
) -> None:
    read = site.get(_DEFINITION).mock(
        side_effect=[
            httpx.Response(200, json={"searchData": {}}),
            httpx.Response(200, json=_shown_to("ada")),
        ]
    )
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    with search_definitions_read_once():
        with pytest.raises(DataParsingError):
            await _read(client)
        assert await _read(client) == "seen by ada"
        assert await _read(client) == "seen by ada"

    assert read.call_count == 2


def _step_routes(site: respx.MockRouter) -> tuple[respx.Route, respx.Route]:
    read = site.get(_DEFINITION).mock(
        return_value=httpx.Response(200, json=_recorded())
    )
    site.post(f"{_SERVICE}/users/1/steps").mock(
        return_value=httpx.Response(200, json={"id": 9})
    )
    site.get(f"{_SERVICE}/users/1/steps/9").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 9,
                "searchName": _SEARCH,
                "searchConfig": {"parameters": _PARAMS},
            },
        )
    )
    put = site.put(f"{_SERVICE}/users/1/steps/9/search-config").mock(
        return_value=httpx.Response(204)
    )
    return read, put


async def _create(api: StrategyAPI) -> None:
    await api.create_step(
        NewStepSpec(
            search_name=_SEARCH, search_config=WDKSearchConfig(parameters=_PARAMS)
        ),
        record_type="transcript",
        user_id="1",
    )


async def _update(api: StrategyAPI) -> None:
    await api.update_step_search_config(
        9,
        WDKSearchConfig(parameters=_PARAMS),
        record_type="transcript",
        search_name=_SEARCH,
        user_id="1",
    )


async def test_outside_a_scope_a_strategy_api_keeps_no_definition_of_its_own(
    site: respx.MockRouter, ada: None
) -> None:
    read, _ = _step_routes(site)
    api = StrategyAPI(VEuPathDBClient(_SERVICE, site_id="plasmodb"))

    await _create(api)
    await _create(api)

    assert read.call_count == 4


async def test_a_save_that_creates_and_updates_steps_reads_the_definition_once(
    site: respx.MockRouter, ada: None
) -> None:
    read, put = _step_routes(site)
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    with search_definitions_read_once():
        await _create(StrategyAPI(client))
        await _create(StrategyAPI(client))
        await _update(StrategyAPI(client))

    assert read.call_count == 1
    organisms = put.calls.last.request.read().decode()
    assert "Plasmodium berghei ANKA" in organisms
    assert '\\"Plasmodium\\"' not in organisms
