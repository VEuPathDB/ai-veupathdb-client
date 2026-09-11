"""One token resolution serves WDK, EDA and VDI."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from veupathdb.auth_context import (
    resolve_veupathdb_auth_token,
    veupathdb_auth_token_ctx,
)
from veupathdb.eda.client import EdaClient
from veupathdb.errors import WDKLoginRequiredError
from veupathdb.settings import VEuPathDBSettings, use_veupathdb_settings_source
from veupathdb.wdk._http import HTTPClient
from veupathdb.wdk.site_router import get_site_router
from veupathdb.wdk.vdi.client import VdiClient

SETTINGS_TOKEN = "token-from-settings"
CONSTRUCTOR_TOKEN = "token-from-constructor"
REQUEST_TOKEN = "token-from-contextvar"
EDA_BASE_URL = "https://plasmodb.org/eda"
VDI_BASE_URL = "https://plasmodb.org/vdi"
DATASET_ID = "soV5JEQEcF00p"


@pytest.fixture
def settings_token() -> Iterator[None]:
    """A deployment that exports ``VEUPATHDB_AUTH_TOKEN`` and nothing else."""
    installed = VEuPathDBSettings(veupathdb_auth_token=SETTINGS_TOKEN)
    use_veupathdb_settings_source(lambda: installed)
    yield
    use_veupathdb_settings_source(VEuPathDBSettings)


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
    client = HTTPClient(base_url="https://plasmodb.org/plasmo/service")
    client.auth_token = auth_token
    async with client._client_lock:
        client._client = httpx.AsyncClient(
            base_url=client.base_url, transport=recorder.transport()
        )
    return client


def test_the_contextvar_wins_over_the_constructor_and_the_settings(
    settings_token: None, request_token: None
) -> None:
    del settings_token, request_token

    assert resolve_veupathdb_auth_token(CONSTRUCTOR_TOKEN) == REQUEST_TOKEN


def test_the_constructor_wins_over_the_settings(
    settings_token: None, empty_context: None
) -> None:
    del settings_token, empty_context

    assert resolve_veupathdb_auth_token(CONSTRUCTOR_TOKEN) == CONSTRUCTOR_TOKEN


def test_the_settings_answer_when_nothing_else_carries_a_token(
    settings_token: None, empty_context: None
) -> None:
    del settings_token, empty_context

    assert resolve_veupathdb_auth_token(None) == SETTINGS_TOKEN


def test_no_form_carries_a_token(empty_context: None) -> None:
    del empty_context

    assert resolve_veupathdb_auth_token(None) is None


async def test_eda_reads_the_settings_token_with_an_empty_contextvar(
    settings_token: None, empty_context: None
) -> None:
    del settings_token, empty_context
    recorder = _Recorder(body={"studies": []})
    client = EdaClient(base_url=EDA_BASE_URL, transport=recorder.transport())
    try:
        await client.list_studies()
    finally:
        await client.close()

    assert f"Authorization={SETTINGS_TOKEN}" in recorder.requests[0].headers["cookie"]


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
    settings_token: None, request_token: None
) -> None:
    del settings_token, request_token
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


async def test_eda_refuses_when_no_form_carries_a_token(empty_context: None) -> None:
    del empty_context
    recorder = _Recorder(body={"studies": []})
    client = EdaClient(base_url=EDA_BASE_URL, transport=recorder.transport())
    try:
        with pytest.raises(WDKLoginRequiredError):
            await client.list_studies()
    finally:
        await client.close()

    assert recorder.requests == []


async def test_vdi_reads_the_settings_token_with_an_empty_contextvar(
    settings_token: None, empty_context: None
) -> None:
    del settings_token, empty_context
    recorder = _Recorder(status=204)
    client = VdiClient(base_url=VDI_BASE_URL, transport=recorder.transport())
    try:
        await client.delete(DATASET_ID)
    finally:
        await client.close()

    assert recorder.requests[0].headers["Authorization"] == f"Bearer {SETTINGS_TOKEN}"


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
    settings_token: None, request_token: None
) -> None:
    del settings_token, request_token
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


async def test_wdk_keeps_the_settings_token_for_a_user_independent_read(
    settings_token: None, empty_context: None
) -> None:
    del settings_token, empty_context
    recorder = _Recorder(body=[])
    client = await _wdk_client(recorder, auth_token=None)
    try:
        await client.get("/record-types")
    finally:
        await client.close()

    assert f"Authorization={SETTINGS_TOKEN}" in recorder.requests[0].headers["cookie"]


async def test_wdk_refuses_a_user_path_that_carries_no_request_token(
    settings_token: None, empty_context: None
) -> None:
    """Only the request's own token may reach a WDK account."""
    del settings_token, empty_context
    recorder = _Recorder(body=[])
    client = await _wdk_client(recorder, auth_token=CONSTRUCTOR_TOKEN)
    try:
        with pytest.raises(WDKLoginRequiredError):
            await client.get("/users/current")
    finally:
        await client.close()

    assert recorder.requests == []


def test_the_router_pins_no_token_on_the_client_it_builds(
    settings_token: None, empty_context: None
) -> None:
    """A per-site client reads the settings token per request, not at construction."""
    del settings_token, empty_context
    client = get_site_router().get_client("plasmodb")

    assert client.auth_token is None
    assert resolve_veupathdb_auth_token(client.auth_token) == SETTINGS_TOKEN
