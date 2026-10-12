"""One guest token, minted once, carries every request no researcher token covers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator

import httpx
import jwt
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda.client import EdaClient
from veupathdb.errors import WDKError, WDKLoginRequiredError
from veupathdb.guest_token import GuestTokens, use_guest_tokens
from veupathdb.settings import VEuPathDBSettings, use_veupathdb_settings_source
from veupathdb.wdk._http import HTTPClient

PLASMO_SERVICE = "https://qa.plasmodb.org/plasmo.qa/service"
TOXO_SERVICE = "https://qa.toxodb.org/toxo.qa/service"
PLASMO_EDA = "https://qa.plasmodb.org/eda"
RESEARCHER_TOKEN = "researcher.registered.token"
GUEST_LIFETIME_SECONDS = 432000
SIGNING_KEY = "a-hermetic-signing-key-of-at-least-32-bytes"


def _jwt(*, is_guest: bool, lifetime: int, serial: int) -> str:
    claims = {
        "is_guest": is_guest,
        "exp": int(time.time()) + lifetime,
        "sub": f"guest-{serial}",
    }
    return jwt.encode(claims, SIGNING_KEY, algorithm="HS256")


def _cookies(request: httpx.Request) -> list[str]:
    header = request.headers.get("cookie", "")
    return [pair.strip() for pair in header.split(";") if pair.strip()]


def _authorization(request: httpx.Request) -> list[str]:
    return [
        pair.removeprefix("Authorization=")
        for pair in _cookies(request)
        if pair.startswith("Authorization=")
    ]


class Wire:
    """A site estate: service roots mint guests, every other path answers."""

    def __init__(
        self,
        *,
        is_guest: bool = True,
        lifetime: int = GUEST_LIFETIME_SECONDS,
        set_cookie: bool = True,
    ) -> None:
        self.is_guest = is_guest
        self.lifetime = lifetime
        self.set_cookie = set_cookie
        self.minted: list[str] = []
        self.mints: list[httpx.Request] = []
        self.calls: list[httpx.Request] = []
        self.refused: dict[str, int] = {}
        self.stale_guests: set[str] = set()
        self.echo_authorization: str | None = None

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/service"):
            return self._mint(request)
        self.calls.append(request)
        if request.url.path.endswith("/app"):
            return httpx.Response(200, text="ok")
        sent = _authorization(request)
        headers = {}
        if self.echo_authorization is not None:
            headers["set-cookie"] = (
                f"Authorization={self.echo_authorization};Version=1;Path=/"
            )
        if sent and sent[0] in self.stale_guests:
            return httpx.Response(401, text="Valid API Key required")
        status = self.refused.get(request.url.path)
        if status is not None:
            return httpx.Response(status, text="refused", headers=headers)
        return httpx.Response(200, json={"studies": []}, headers=headers)

    def _mint(self, request: httpx.Request) -> httpx.Response:
        self.mints.append(request)
        if not self.set_cookie:
            return httpx.Response(200, json={})
        token = _jwt(
            is_guest=self.is_guest, lifetime=self.lifetime, serial=len(self.minted)
        )
        self.minted.append(token)
        return httpx.Response(
            200,
            json={},
            headers={
                "set-cookie": f"Authorization={token};Version=1;Path=/;Max-Age=94608000"
            },
        )


@pytest.fixture
def wire() -> Wire:
    estate = Wire()
    use_guest_tokens(GuestTokens(transport=estate.transport()))
    return estate


@pytest.fixture
def no_request_token() -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set(None)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


def _wdk(wire: Wire, base_url: str = PLASMO_SERVICE) -> HTTPClient:
    return HTTPClient(base_url=base_url, transport=wire.transport())


def _eda(wire: Wire) -> EdaClient:
    return EdaClient(base_url=PLASMO_EDA, transport=wire.transport())


@pytest.mark.usefixtures("no_request_token")
async def test_one_mint_serves_two_sites_and_eda(wire: Wire) -> None:
    plasmo, toxo, eda = _wdk(wire), _wdk(wire, TOXO_SERVICE), _eda(wire)
    try:
        await plasmo.get("/record-types")
        await toxo.get("/record-types")
        await eda.list_studies()
        await plasmo.get("/ontologies/Categories")
    finally:
        await plasmo.close()
        await toxo.close()
        await eda.close()

    assert len(wire.minted) == 1
    assert [_authorization(call) for call in wire.calls] == [wire.minted] * len(
        wire.calls
    )
    assert {call.url.path for call in wire.calls} >= {
        "/plasmo.qa/service/record-types",
        "/toxo.qa/service/record-types",
        "/eda/studies",
    }


@pytest.mark.usefixtures("no_request_token")
async def test_the_mint_carries_no_cookie(wire: Wire) -> None:
    client = _wdk(wire)
    try:
        await client.get("/record-types")
    finally:
        await client.close()

    assert [_cookies(mint) for mint in wire.mints] == [[]]
    assert str(wire.mints[0].url) == PLASMO_SERVICE


async def test_concurrent_callers_share_one_mint(wire: Wire) -> None:
    tokens = GuestTokens(transport=wire.transport())

    held = await asyncio.gather(*(tokens.token(PLASMO_SERVICE) for _ in range(5)))

    assert len(wire.minted) == 1
    assert set(held) == set(wire.minted)


async def test_a_token_near_its_expiry_is_minted_again() -> None:
    wire = Wire(lifetime=60)
    tokens = GuestTokens(transport=wire.transport())

    first = await tokens.token(PLASMO_SERVICE)
    second = await tokens.token(PLASMO_SERVICE)

    assert wire.minted == [first, second]
    assert first != second


async def test_a_fresh_token_is_reused() -> None:
    wire = Wire()
    tokens = GuestTokens(transport=wire.transport())

    first = await tokens.token(PLASMO_SERVICE)
    second = await tokens.token(TOXO_SERVICE)

    assert first == second
    assert len(wire.mints) == 1


async def test_a_registered_token_is_refused_as_the_guest() -> None:
    tokens = GuestTokens(transport=Wire(is_guest=False).transport())

    with pytest.raises(WDKError, match="not a guest"):
        await tokens.token(PLASMO_SERVICE)


async def test_a_mint_with_no_cookie_is_refused() -> None:
    tokens = GuestTokens(transport=Wire(set_cookie=False).transport())

    with pytest.raises(WDKError, match="no guest"):
        await tokens.token(PLASMO_SERVICE)


@pytest.mark.usefixtures("no_request_token")
async def test_a_401_mints_again_and_retries_once(wire: Wire) -> None:
    client = _wdk(wire)
    try:
        await client.get("/record-types")
        wire.stale_guests.add(wire.minted[0])
        assert await client.get("/record-types") == {"studies": []}
    finally:
        await client.close()

    reads = [c for c in wire.calls if c.url.path.endswith("/record-types")]
    assert len(wire.minted) == 2
    assert [_authorization(r) for r in reads] == [
        [wire.minted[0]],
        [wire.minted[0]],
        [wire.minted[1]],
    ]


@pytest.mark.usefixtures("no_request_token")
async def test_a_second_401_is_login_required_and_not_retried(wire: Wire) -> None:
    wire.refused["/plasmo.qa/service/record-types"] = 401
    client = _wdk(wire)
    try:
        with pytest.raises(WDKLoginRequiredError):
            await client.get("/record-types")
    finally:
        await client.close()

    reads = [c for c in wire.calls if c.url.path.endswith("/record-types")]
    assert len(wire.minted) == 2
    assert len(reads) == 2


@pytest.mark.usefixtures("no_request_token")
async def test_a_keyed_path_refused_to_the_guest_is_login_required(
    wire: Wire,
) -> None:
    wire.refused["/plasmo.qa/service/record-types/transcript/searches"] = 403
    client = _wdk(wire)
    try:
        with pytest.raises(WDKLoginRequiredError):
            await client.get("/record-types/transcript/searches")
    finally:
        await client.close()

    assert len(wire.minted) == 1


async def test_a_403_to_the_researcher_stays_a_wdk_error(wire: Wire) -> None:
    wire.refused["/plasmo.qa/service/record-types/transcript/searches"] = 403
    veupathdb_auth_token_ctx.set(RESEARCHER_TOKEN)
    client = _wdk(wire)
    try:
        with pytest.raises(WDKError) as raised:
            await client.get("/record-types/transcript/searches")
    finally:
        await client.close()

    assert raised.value.status == 403
    assert wire.minted == []


async def test_the_researcher_token_wins_over_the_guest(wire: Wire) -> None:
    veupathdb_auth_token_ctx.set(RESEARCHER_TOKEN)
    client, eda = _wdk(wire), _eda(wire)
    try:
        await client.get("/record-types/transcript/searches")
        await eda.list_studies()
    finally:
        await client.close()
        await eda.close()

    assert wire.mints == []
    assert {tuple(_authorization(call)) for call in wire.calls} == {(RESEARCHER_TOKEN,)}


async def test_a_switch_from_the_guest_to_a_researcher_starts_a_new_session(
    wire: Wire,
) -> None:
    client = _wdk(wire)
    try:
        reset = veupathdb_auth_token_ctx.set(None)
        await client.get("/record-types")
        veupathdb_auth_token_ctx.reset(reset)
        veupathdb_auth_token_ctx.set(RESEARCHER_TOKEN)
        await client.get("/record-types")
    finally:
        await client.close()

    sessions = [c for c in wire.calls if c.url.path.endswith("/app")]
    assert [_authorization(s) for s in sessions] == [
        wire.minted,
        [RESEARCHER_TOKEN],
    ]


async def test_the_jar_never_resends_a_server_set_authorization(wire: Wire) -> None:
    wire.echo_authorization = "server-set-value"
    veupathdb_auth_token_ctx.set(RESEARCHER_TOKEN)
    client = _wdk(wire)
    try:
        await client.get("/record-types")
        jar = await client._get_client()
        stored = [cookie.name for cookie in jar.cookies.jar]
        await client.get("/record-types")
    finally:
        await client.close()

    assert "Authorization" not in stored
    assert [_authorization(call) for call in wire.calls] == [[RESEARCHER_TOKEN]] * len(
        wire.calls
    )


@pytest.mark.usefixtures("no_request_token")
async def test_eda_mints_again_and_retries_once_after_a_401(wire: Wire) -> None:
    eda = _eda(wire)
    try:
        await eda.list_studies()
        wire.stale_guests.add(wire.minted[0])
        await eda.list_studies()
    finally:
        await eda.close()

    assert len(wire.minted) == 2
    assert [_authorization(c) for c in wire.calls] == [
        [wire.minted[0]],
        [wire.minted[0]],
        [wire.minted[1]],
    ]


@pytest.mark.usefixtures("no_request_token")
async def test_no_deployment_token_reaches_a_request(
    wire: Wire, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VEUPATHDB_AUTH_TOKEN", "deployment.account.token")
    installed = VEuPathDBSettings()
    use_veupathdb_settings_source(lambda: installed)
    client, eda = _wdk(wire), _eda(wire)
    try:
        await client.get("/record-types")
        await eda.list_studies()
    finally:
        await client.close()
        await eda.close()

    assert "veupathdb_auth_token" not in VEuPathDBSettings.model_fields
    assert {tuple(_authorization(call)) for call in wire.calls} == {tuple(wire.minted)}
