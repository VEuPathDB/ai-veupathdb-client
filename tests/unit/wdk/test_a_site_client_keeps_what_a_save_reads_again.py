"""The site client keeps the user id each token names and each boolean search, so
the strategy APIs a host builds per call read them from WDK once."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.strategy_api.helpers import resolve_wdk_user_id

_SERVICE = "https://qa.plasmodb.org/plasmo.qa/service"
_WEBAPP = "https://qa.plasmodb.org/plasmo.qa/app"
_BOOLEAN = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"
_IDS = {"token-of-ada": 101, "token-of-bea": 202}


def _as(token: str) -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set(token)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


def _who(request: httpx.Request) -> httpx.Response:
    cookie = request.headers.get("cookie", "")
    token = next(t for t in _IDS if f"Authorization={t}" in cookie)
    return httpx.Response(200, json={"id": _IDS[token], "isGuest": False})


@pytest.fixture
def site() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(_WEBAPP).mock(return_value=httpx.Response(200, text=""))
        yield router


async def _user_id(client: VEuPathDBClient, token: str) -> str:
    for _ in _as(token):
        return await StrategyAPI(client)._get_user_id(None)
    raise AssertionError


async def test_two_strategy_apis_of_one_site_read_the_user_once(
    site: respx.MockRouter,
) -> None:
    current = site.get(f"{_SERVICE}/users/current").mock(side_effect=_who)
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    first = await _user_id(client, "token-of-ada")
    second = await _user_id(client, "token-of-ada")

    assert (first, second, current.call_count) == ("101", "101", 1)


async def test_each_token_is_answered_with_its_own_user(
    site: respx.MockRouter,
) -> None:
    current = site.get(f"{_SERVICE}/users/current").mock(side_effect=_who)
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    ada = await _user_id(client, "token-of-ada")
    bea = await _user_id(client, "token-of-bea")
    ada_again = await _user_id(client, "token-of-ada")

    assert (ada, bea, ada_again) == ("101", "202", "101")
    assert current.call_count == 2


async def test_an_unreadable_answer_is_not_kept(site: respx.MockRouter) -> None:
    current = site.get(f"{_SERVICE}/users/current").mock(
        side_effect=[
            httpx.Response(200, json={"isGuest": False}),
            httpx.Response(200, json={"id": 101, "isGuest": False}),
        ]
    )
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")
    for _ in _as("token-of-ada"):
        assert await resolve_wdk_user_id(client) is None
        assert await resolve_wdk_user_id(client) == "101"

    assert current.call_count == 2


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_boolean_transcript.json"), reason=NEEDS_QA_RECORDING
)
async def test_two_strategy_apis_of_one_site_read_the_boolean_search_once(
    site: respx.MockRouter,
) -> None:
    details = load_recorded("search_boolean_transcript").json_body()
    assert isinstance(details, dict)
    listed = site.get(f"{_SERVICE}/record-types/transcript/searches").mock(
        return_value=httpx.Response(200, json=[details["searchData"]])
    )
    read = site.get(f"{_SERVICE}/record-types/transcript/searches/{_BOOLEAN}").mock(
        return_value=httpx.Response(200, json=details)
    )
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    first = await StrategyAPI(client).client.boolean_search("transcript")
    second = await StrategyAPI(client).client.boolean_search("transcript")

    assert first == second
    assert (
        first.search_name,
        first.left_param,
        first.right_param,
        first.operator_param,
    ) == (
        _BOOLEAN,
        "bq_left_op_TranscriptRecordClasses_TranscriptRecordClass",
        "bq_right_op_TranscriptRecordClasses_TranscriptRecordClass",
        "bq_operator",
    )
    assert (listed.call_count, read.call_count) == (1, 1)


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_boolean_transcript.json"), reason=NEEDS_QA_RECORDING
)
async def test_each_site_client_reads_its_own_boolean_search(
    site: respx.MockRouter,
) -> None:
    details = load_recorded("search_boolean_transcript").json_body()
    assert isinstance(details, dict)
    listed = site.get(f"{_SERVICE}/record-types/transcript/searches").mock(
        return_value=httpx.Response(200, json=[details["searchData"]])
    )
    site.get(f"{_SERVICE}/record-types/transcript/searches/{_BOOLEAN}").mock(
        return_value=httpx.Response(200, json=details)
    )

    await VEuPathDBClient(_SERVICE, site_id="plasmodb").boolean_search("transcript")
    await VEuPathDBClient(_SERVICE, site_id="plasmodb").boolean_search("transcript")

    assert listed.call_count == 2


async def test_a_request_with_no_login_token_keeps_nothing(
    site: respx.MockRouter,
) -> None:
    current = site.get(f"{_SERVICE}/users/current").mock(side_effect=_who)
    client = VEuPathDBClient(_SERVICE, site_id="plasmodb")

    async def read() -> str | None:
        return "999"

    assert await client.remembered_user_id(read) == "999"
    assert await _user_id(client, "token-of-ada") == "101"
    assert current.call_count == 1
