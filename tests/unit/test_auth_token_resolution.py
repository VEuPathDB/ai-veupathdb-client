"""How WDK, EDA and VDI resolve the token a request travels with.

A call on a researcher's own data never travels as the shared guest.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from tests.unit.wdk.vdi._wire import no_request_transport

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda.analyses import EdaAnalysesClient
from veupathdb.eda.client import EdaClient
from veupathdb.errors import WDKLoginRequiredError
from veupathdb.testing import HERMETIC_GUEST_TOKEN
from veupathdb.wdk._http import HTTPClient
from veupathdb.wdk.site_router import get_site_router
from veupathdb.wdk.vdi.client import VdiClient

CONSTRUCTOR_TOKEN = "token-from-constructor"
REQUEST_TOKEN = "token-from-contextvar"
EDA_BASE_URL = "https://qa.plasmodb.org/eda"
VDI_BASE_URL = "https://qa.plasmodb.org/vdi"
DATASET_ID = "vdiTestData01"
PROJECT_ID = "PlasmoDB"
WDK_USER_ID = "1000000102"


@pytest.fixture
def empty_context() -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set(None)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


@pytest.fixture
def request_token() -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set(REQUEST_TOKEN)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


class _Recorder:
    """Answers one response and keeps every request it was sent."""

    def __init__(self, status: int = 200, body: object = None) -> None:
        self._status = status
        self._body = body
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if self._body is None:
                return httpx.Response(self._status)
            return httpx.Response(self._status, json=self._body)

        return httpx.MockTransport(handle)


async def _wdk_client(recorder: _Recorder, auth_token: str | None) -> HTTPClient:
    """A WDK client whose transport answers without reaching a site."""
    client = HTTPClient(base_url="https://qa.plasmodb.org/plasmo.qa/service")
    client.auth_token = auth_token
    async with client._client_lock:
        client._client = httpx.AsyncClient(
            base_url=client.base_url, transport=recorder.transport()
        )
    return client


async def test_eda_refuses_the_guest_on_a_user_path(empty_context: None) -> None:
    """An analysis is the researcher's own, so the guest never reads it."""
    del empty_context
    client = EdaClient(base_url=EDA_BASE_URL, transport=no_request_transport())
    analyses = EdaAnalysesClient(client=client, project_id=PROJECT_ID)
    try:
        with pytest.raises(WDKLoginRequiredError):
            await analyses.list_all(user_id=WDK_USER_ID)
    finally:
        await client.close()


async def test_eda_sends_the_request_token_on_a_user_path(
    request_token: None,
) -> None:
    del request_token
    recorder = _Recorder(body=[])
    client = EdaClient(base_url=EDA_BASE_URL, transport=recorder.transport())
    analyses = EdaAnalysesClient(client=client, project_id=PROJECT_ID)
    try:
        await analyses.list_all(user_id=WDK_USER_ID)
    finally:
        await client.close()

    assert f"Authorization={REQUEST_TOKEN}" in recorder.requests[0].headers["cookie"]


async def test_eda_sends_the_constructor_token_on_a_user_path(
    empty_context: None,
) -> None:
    del empty_context
    recorder = _Recorder(body=[])
    client = EdaClient(
        base_url=EDA_BASE_URL,
        transport=recorder.transport(),
        auth_token=CONSTRUCTOR_TOKEN,
    )
    analyses = EdaAnalysesClient(client=client, project_id=PROJECT_ID)
    try:
        await analyses.list_all(user_id=WDK_USER_ID)
    finally:
        await client.close()

    assert (
        f"Authorization={CONSTRUCTOR_TOKEN}" in recorder.requests[0].headers["cookie"]
    )


async def test_eda_reads_the_constructor_token_with_an_empty_contextvar(
    empty_context: None,
) -> None:
    del empty_context
    recorder = _Recorder(body={"studies": []})
    client = EdaClient(
        base_url=EDA_BASE_URL,
        transport=recorder.transport(),
        auth_token=CONSTRUCTOR_TOKEN,
    )
    try:
        await client.list_studies()
    finally:
        await client.close()

    assert (
        f"Authorization={CONSTRUCTOR_TOKEN}" in recorder.requests[0].headers["cookie"]
    )


async def test_eda_lets_the_contextvar_override_both(
    request_token: None,
) -> None:
    del request_token
    recorder = _Recorder(body={"studies": []})
    client = EdaClient(
        base_url=EDA_BASE_URL,
        transport=recorder.transport(),
        auth_token=CONSTRUCTOR_TOKEN,
    )
    try:
        await client.list_studies()
    finally:
        await client.close()

    assert f"Authorization={REQUEST_TOKEN}" in recorder.requests[0].headers["cookie"]


async def test_eda_sends_the_guest_when_no_form_carries_a_token(
    empty_context: None,
) -> None:
    del empty_context
    recorder = _Recorder(body={"studies": []})
    client = EdaClient(base_url=EDA_BASE_URL, transport=recorder.transport())
    try:
        await client.list_studies()
    finally:
        await client.close()

    assert recorder.requests[0].headers["cookie"] == (
        f"Authorization={HERMETIC_GUEST_TOKEN}"
    )


async def test_vdi_refuses_the_guest_with_an_empty_contextvar(
    empty_context: None,
) -> None:
    """A dataset is the researcher's own, so the guest never reads it."""
    del empty_context
    client = VdiClient(base_url=VDI_BASE_URL, transport=no_request_transport())
    try:
        with pytest.raises(WDKLoginRequiredError):
            await client.get(DATASET_ID)
    finally:
        await client.close()


async def test_vdi_reads_the_constructor_token_with_an_empty_contextvar(
    empty_context: None,
) -> None:
    del empty_context
    recorder = _Recorder(status=204)
    client = VdiClient(
        base_url=VDI_BASE_URL,
        transport=recorder.transport(),
        auth_token=CONSTRUCTOR_TOKEN,
    )
    try:
        await client.delete(DATASET_ID)
    finally:
        await client.close()

    assert (
        recorder.requests[0].headers["Authorization"] == f"Bearer {CONSTRUCTOR_TOKEN}"
    )


async def test_vdi_lets_the_contextvar_override_both(
    request_token: None,
) -> None:
    del request_token
    recorder = _Recorder(status=204)
    client = VdiClient(
        base_url=VDI_BASE_URL,
        transport=recorder.transport(),
        auth_token=CONSTRUCTOR_TOKEN,
    )
    try:
        await client.delete(DATASET_ID)
    finally:
        await client.close()

    assert recorder.requests[0].headers["Authorization"] == f"Bearer {REQUEST_TOKEN}"


async def test_vdi_refuses_when_no_form_carries_a_token(empty_context: None) -> None:
    del empty_context
    recorder = _Recorder(status=204)
    client = VdiClient(base_url=VDI_BASE_URL, transport=recorder.transport())
    try:
        with pytest.raises(WDKLoginRequiredError):
            await client.delete(DATASET_ID)
    finally:
        await client.close()

    assert recorder.requests == []


async def test_wdk_sends_the_guest_for_a_user_independent_read(
    empty_context: None,
) -> None:
    del empty_context
    recorder = _Recorder(body=[])
    client = await _wdk_client(recorder, auth_token=None)
    try:
        await client.get("/record-types")
    finally:
        await client.close()

    assert {request.headers["cookie"] for request in recorder.requests} == {
        f"Authorization={HERMETIC_GUEST_TOKEN}"
    }


async def test_wdk_refuses_a_user_path_that_carries_no_request_token(
    empty_context: None,
) -> None:
    """Only the request's own token may reach a WDK account."""
    del empty_context
    recorder = _Recorder(body=[])
    client = await _wdk_client(recorder, auth_token=CONSTRUCTOR_TOKEN)
    try:
        with pytest.raises(WDKLoginRequiredError):
            await client.get("/users/current")
    finally:
        await client.close()

    assert recorder.requests == []


def test_the_router_pins_no_token_on_the_client_it_builds(empty_context: None) -> None:
    """A per-site client resolves its token per request, not at construction."""
    del empty_context
    client = get_site_router().get_client("plasmodb")

    assert client.auth_token is None
