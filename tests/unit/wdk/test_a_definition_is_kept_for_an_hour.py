"""A site client keeps each search definition and record type it reads for an
hour, under the login that asked."""

from __future__ import annotations

import asyncio
import copy
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
from tests.unit.wdk._virtual_clock import on_the_virtual_clock

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.json_types import JSONObject
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import held_reads
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import NewStepSpec, WDKSearchConfig

pytestmark = pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_molecular_weight.json"),
    reason=NEEDS_QA_RECORDING,
)

_PLASMO = "https://qa.plasmodb.org/plasmo.qa/service"
_TOXO = "https://qa.toxodb.org/toxo.qa/service"
_CRYPTO = "https://qa.cryptodb.org/cryptodb.qa/service"
_SEARCH = "GenesByMolecularWeight"
_DEFINITION = f"/record-types/transcript/searches/{_SEARCH}"
_RECORD_TYPE = "/record-types/transcript"
_ONE_HOUR = 60 * 60
_PARAMS = {
    "organism": '["Plasmodium"]',
    "min_molecular_weight": "10000",
    "max_molecular_weight": "20000",
}


def _shown_to(login: str) -> JSONObject:
    body = load_recorded("search_genes_by_molecular_weight").json_body()
    assert isinstance(body, dict)
    shown = copy.deepcopy(body)
    search = shown["searchData"]
    assert isinstance(search, dict)
    search["displayName"] = f"seen by {login}"
    return shown


class _Site:
    def __init__(self, service: str) -> None:
        self.prefix = httpx.URL(service).path
        self.sent: Counter[tuple[str, str | None]] = Counter()

    def client(self, service: str) -> VEuPathDBClient:
        return VEuPathDBClient(service, transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix(self.prefix)
        if path.endswith("/app"):
            return httpx.Response(200, text="")
        cookie = request.headers.get("cookie", "")
        login = next(
            t for t in ("ada", "bea") if f"Authorization=token-of-{t}" in cookie
        )
        self.sent[(path, request.url.params.get("expandParams"))] += 1
        if path == _RECORD_TYPE:
            return httpx.Response(
                200, json={"urlSegment": "transcript", "displayName": f"for {login}"}
            )
        if path.endswith("/steps/9/search-config"):
            return httpx.Response(204)
        if path.endswith("/steps/9"):
            return httpx.Response(
                200,
                json={
                    "id": 9,
                    "searchName": _SEARCH,
                    "searchConfig": {"parameters": _PARAMS},
                },
            )
        if path.endswith("/steps"):
            return httpx.Response(200, json={"id": 9})
        return httpx.Response(200, json=_shown_to(login))


@contextmanager
def _as(login: str) -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set(f"token-of-{login}")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


async def _read(client: VEuPathDBClient, *, expand: bool = True) -> str:
    details = await client.get_search_details(
        "transcript", _SEARCH, expand_params=expand
    )
    return details.search_data.display_name


def test_a_second_read_inside_an_hour_sends_nothing() -> None:
    site = _Site(_PLASMO)
    client = site.client(_PLASMO)
    seen: list[str] = []

    async def scenario() -> None:
        with _as("ada"):
            seen.append(await _read(client))
            await asyncio.sleep(_ONE_HOUR - 1)
            seen.append(await _read(client))

    on_the_virtual_clock(scenario())

    assert seen == ["seen by ada", "seen by ada"]
    assert site.sent[(_DEFINITION, "true")] == 1


def test_a_read_after_an_hour_sends_one() -> None:
    site = _Site(_PLASMO)
    client = site.client(_PLASMO)

    async def scenario() -> None:
        with _as("ada"):
            await _read(client)
            await asyncio.sleep(_ONE_HOUR)
            await _read(client)
            await _read(client)

    on_the_virtual_clock(scenario())

    assert site.sent[(_DEFINITION, "true")] == 2


def test_a_record_type_is_kept_for_an_hour() -> None:
    site = _Site(_PLASMO)
    api = StrategyAPI(site.client(_PLASMO))
    names: list[str] = []

    async def scenario() -> None:
        with _as("ada"):
            for wait in (0, 60, _ONE_HOUR - 61, 1, 0):
                await asyncio.sleep(wait)
                names.append(
                    (await api.get_record_type_info("transcript")).display_name
                )

    on_the_virtual_clock(scenario())

    assert names == ["for ada"] * 5
    assert site.sent[(_RECORD_TYPE, None)] == 2


async def test_each_login_reads_its_own_definition() -> None:
    site = _Site(_PLASMO)
    client = site.client(_PLASMO)

    with _as("ada"):
        ada = await _read(client)
    with _as("bea"):
        bea = await _read(client)
    with _as("ada"):
        ada_again = await _read(client)

    assert (ada, bea, ada_again) == ("seen by ada", "seen by bea", "seen by ada")
    assert site.sent[(_DEFINITION, "true")] == 2


async def test_the_plain_and_the_expanded_definition_are_kept_apart() -> None:
    site = _Site(_PLASMO)
    client = site.client(_PLASMO)

    with _as("ada"):
        for expand in (True, False, True, False):
            await _read(client, expand=expand)

    assert (site.sent[(_DEFINITION, "true")], site.sent[(_DEFINITION, None)]) == (1, 1)


async def test_each_site_reads_its_own_definition() -> None:
    plasmo = _Site(_PLASMO)
    toxo = _Site(_TOXO)

    with _as("ada"):
        await _read(plasmo.client(_PLASMO))
        await _read(toxo.client(_TOXO))

    assert (plasmo.sent[(_DEFINITION, "true")], toxo.sent[(_DEFINITION, "true")]) == (
        1,
        1,
    )


async def test_steps_written_one_after_another_read_the_definition_once() -> None:
    site = _Site(_PLASMO)
    api = StrategyAPI(site.client(_PLASMO), user_id="1")
    spec = NewStepSpec(
        search_name=_SEARCH, search_config=WDKSearchConfig(parameters=_PARAMS)
    )

    with _as("ada"):
        await api.create_step(spec, record_type="transcript")
        await api.create_step(spec, record_type="transcript")
        await api.update_step_search_config(
            9,
            WDKSearchConfig(parameters=_PARAMS),
            record_type="transcript",
            search_name=_SEARCH,
        )

    assert site.sent[(_DEFINITION, "true")] == 1


def _padded_site(sent: list[str], size: int) -> httpx.MockTransport:
    padding = "x" * size

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/app"):
            return httpx.Response(200, text="")
        sent.append(f"{request.url.host}{request.url.path.rsplit('/', 1)[-1]}")
        name = f"{request.url.host}/{request.url.path.rsplit('/', 1)[-1]}"
        return httpx.Response(200, json={"urlSegment": name, "displayName": padding})

    return httpx.MockTransport(handle)


async def test_the_process_keeps_at_most_64_mib_dropping_the_least_used() -> None:
    sent: list[str] = []
    size = 8 * 1024 * 1024 - 100
    plasmo = StrategyAPI(
        VEuPathDBClient(_PLASMO, transport=_padded_site(sent, size)), user_id="1"
    )
    toxo = StrategyAPI(
        VEuPathDBClient(_TOXO, transport=_padded_site(sent, size)), user_id="1"
    )
    with _as("ada"):
        for n in range(4):
            await plasmo.get_record_type_info(f"type{n}")
            await toxo.get_record_type_info(f"type{n}")
        await plasmo.get_record_type_info("type0")
        await toxo.get_record_type_info("type4")
        await plasmo.get_record_type_info("type0")
        await toxo.get_record_type_info("type0")

    assert sent[8:] == ["qa.toxodb.orgtype4", "qa.toxodb.orgtype0"]
    assert held_reads.definitions().held_bytes <= held_reads.DEFINITION_BYTES


async def test_two_logins_reading_one_definition_hold_one_copy() -> None:
    sent: list[str] = []
    client = VEuPathDBClient(_PLASMO, transport=_padded_site(sent, 1000))
    api = StrategyAPI(client, user_id="1")
    with _as("ada"):
        await api.get_record_type_info("transcript")
    one = held_reads.definitions().held_bytes
    with _as("bea"):
        await api.get_record_type_info("transcript")

    assert len(sent) == 2
    assert held_reads.definitions().held_bytes == one


async def test_two_logins_with_different_answers_each_read_their_own() -> None:
    site = _Site(_PLASMO)
    client = site.client(_PLASMO)

    with _as("ada"):
        ada = await _read(client)
    with _as("bea"):
        bea = await _read(client)
    with _as("ada"):
        ada_again = await _read(client)
    with _as("bea"):
        bea_again = await _read(client)

    assert (ada, bea, ada_again, bea_again) == (
        "seen by ada",
        "seen by bea",
        "seen by ada",
        "seen by bea",
    )


async def test_a_dropped_key_leaves_the_text_another_key_holds() -> None:
    sent: list[str] = []
    mib = 1024 * 1024
    shared = StrategyAPI(
        VEuPathDBClient(_PLASMO, transport=_padded_site(sent, 30 * mib)), user_id="1"
    )
    large = StrategyAPI(
        VEuPathDBClient(_TOXO, transport=_padded_site(sent, 30 * mib)), user_id="1"
    )
    small = StrategyAPI(
        VEuPathDBClient(_CRYPTO, transport=_padded_site(sent, 10 * mib)),
        user_id="1",
    )
    with _as("ada"):
        await shared.get_record_type_info("transcript")
    with _as("bea"):
        await shared.get_record_type_info("transcript")
    with _as("ada"):
        await large.get_record_type_info("gene")
    with _as("bea"):
        await shared.get_record_type_info("transcript")
    with _as("ada"):
        await small.get_record_type_info("gene")
    with _as("bea"):
        await shared.get_record_type_info("transcript")
    with _as("ada"):
        await shared.get_record_type_info("transcript")

    assert sent == [
        "qa.plasmodb.orgtranscript",
        "qa.plasmodb.orgtranscript",
        "qa.toxodb.orggene",
        "qa.cryptodb.orggene",
        "qa.plasmodb.orgtranscript",
    ]
    assert held_reads.definitions().held_bytes < held_reads.DEFINITION_BYTES


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(200, text=""),
        httpx.Response(200, json={"searchData": {}}),
        httpx.Response(200, json=["not", "a", "definition"]),
    ],
)
async def test_an_empty_or_unreadable_definition_is_not_kept(
    answer: httpx.Response,
) -> None:
    sent: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/app"):
            return httpx.Response(200, text="")
        sent.append(request.url.path)
        return answer

    client = VEuPathDBClient(_PLASMO, transport=httpx.MockTransport(handle))
    with _as("ada"):
        for _ in range(2):
            await client.get(_DEFINITION, params={"expandParams": "true"})

    assert len(sent) == 2
