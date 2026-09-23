"""Reading ``GET /users/current``: the typed profile and the registered email.

None means the site answered and the token names no registered user. A site
that does not answer raises, so a host never reads an outage as signed out.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import SiteNotFoundError, WDKError
from veupathdb.wdk import current_user
from veupathdb.wdk.current_user import fetch_current_user, resolve_registered_email
from veupathdb.wdk.wdk_models import WDKUserInfo

_WEBAPP = "https://plasmodb.org/plasmo/app"
_CURRENT_USER = "https://plasmodb.org/plasmo/service/users/current"

_REGISTERED = {
    "id": 12345678,
    "email": "someone@example.org",
    "isGuest": False,
    "properties": {
        "firstName": "Ada",
        "lastName": "Lovelace",
        "organization": "Analytical Engine",
    },
}


def _allow_session_init() -> None:
    """The transport opens a WDK session before the first credentialed call."""
    respx.get(_WEBAPP).mock(return_value=httpx.Response(200, text=""))


def test_the_properties_carry_the_first_and_last_name() -> None:
    user = WDKUserInfo.model_validate(_REGISTERED)
    assert user.properties.first_name == "Ada"
    assert user.properties.last_name == "Lovelace"


def test_absent_properties_leave_both_names_unset() -> None:
    user = WDKUserInfo.model_validate({"id": 1, "isGuest": True})
    assert user.properties.first_name is None
    assert user.properties.last_name is None


async def test_no_token_reads_nobody() -> None:
    reset = veupathdb_auth_token_ctx.set(None)
    try:
        assert await fetch_current_user("plasmodb") is None
    finally:
        veupathdb_auth_token_ctx.reset(reset)


@respx.mock
async def test_a_token_reads_the_registered_user() -> None:
    _allow_session_init()
    respx.get(_CURRENT_USER).mock(return_value=httpx.Response(200, json=_REGISTERED))
    reset = veupathdb_auth_token_ctx.set("a-token")
    try:
        user = await fetch_current_user("plasmodb")
    finally:
        veupathdb_auth_token_ctx.reset(reset)

    assert user is not None
    assert user.id == 12345678
    assert user.is_guest is False
    assert user.properties.first_name == "Ada"
    assert user.properties.last_name == "Lovelace"


@respx.mock
async def test_a_refused_token_names_nobody() -> None:
    _allow_session_init()
    respx.get(_CURRENT_USER).mock(return_value=httpx.Response(401, text="no"))
    reset = veupathdb_auth_token_ctx.set("a-token")
    try:
        assert await fetch_current_user("plasmodb") is None
    finally:
        veupathdb_auth_token_ctx.reset(reset)


@respx.mock
async def test_a_guest_answer_is_the_guest_profile() -> None:
    _allow_session_init()
    guest = {"id": 99, "email": "guest@veupathdb.org", "isGuest": True}
    respx.get(_CURRENT_USER).mock(return_value=httpx.Response(200, json=guest))
    reset = veupathdb_auth_token_ctx.set("a-token")
    try:
        user = await fetch_current_user("plasmodb")
    finally:
        veupathdb_auth_token_ctx.reset(reset)

    assert user is not None
    assert user.is_guest is True


@respx.mock
async def test_a_server_error_raises_with_its_status() -> None:
    _allow_session_init()
    route = respx.get(_CURRENT_USER).mock(return_value=httpx.Response(503, text="down"))
    reset = veupathdb_auth_token_ctx.set("a-token")
    try:
        with pytest.raises(WDKError) as raised:
            await fetch_current_user("plasmodb")
    finally:
        veupathdb_auth_token_ctx.reset(reset)

    assert raised.value.status == 503
    assert route.call_count == 1


@respx.mock
async def test_a_transport_timeout_is_not_retried() -> None:
    _allow_session_init()
    route = respx.get(_CURRENT_USER).mock(side_effect=httpx.ReadTimeout("slow"))
    reset = veupathdb_auth_token_ctx.set("a-token")
    try:
        with pytest.raises(WDKError) as raised:
            await fetch_current_user("plasmodb")
    finally:
        veupathdb_auth_token_ctx.reset(reset)

    assert raised.value.status == 502
    assert route.call_count == 1


def test_the_identity_deadline_is_ten_seconds() -> None:
    assert current_user.IDENTITY_READ_TIMEOUT_SECONDS == 10.0


@respx.mock
async def test_a_read_past_the_deadline_raises_after_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(current_user, "IDENTITY_READ_TIMEOUT_SECONDS", 0.05)
    _allow_session_init()

    sent: list[httpx.Request] = []

    async def never_answers(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        await asyncio.sleep(5)
        return httpx.Response(200, json=_REGISTERED)

    respx.get(_CURRENT_USER).mock(side_effect=never_answers)
    reset = veupathdb_auth_token_ctx.set("a-token")
    started = time.monotonic()
    try:
        with pytest.raises(WDKError) as raised:
            await fetch_current_user("plasmodb")
    finally:
        veupathdb_auth_token_ctx.reset(reset)

    assert raised.value.status == 502
    assert len(sent) == 1
    assert time.monotonic() - started < 1.0


async def test_an_unknown_site_raises() -> None:
    reset = veupathdb_auth_token_ctx.set("a-token")
    try:
        with pytest.raises(SiteNotFoundError):
            await fetch_current_user("nosuchsite")
    finally:
        veupathdb_auth_token_ctx.reset(reset)


@respx.mock
async def test_the_registered_email_comes_from_the_token_the_caller_passes() -> None:
    _allow_session_init()
    respx.get(_CURRENT_USER).mock(return_value=httpx.Response(200, json=_REGISTERED))
    assert (
        await resolve_registered_email("a-token", "plasmodb") == "someone@example.org"
    )
    assert veupathdb_auth_token_ctx.get() is None


@respx.mock
async def test_a_guest_has_no_registered_email() -> None:
    _allow_session_init()
    guest = {"id": 99, "email": "guest@veupathdb.org", "isGuest": True}
    respx.get(_CURRENT_USER).mock(return_value=httpx.Response(200, json=guest))
    assert await resolve_registered_email("a-token", "plasmodb") is None


@respx.mock
async def test_the_caller_token_is_restored_when_the_read_fails() -> None:
    _allow_session_init()
    respx.get(_CURRENT_USER).mock(side_effect=httpx.ConnectError("refused"))
    reset = veupathdb_auth_token_ctx.set("outer-token")
    try:
        with pytest.raises(WDKError):
            await resolve_registered_email("inner-token", "plasmodb")
        assert veupathdb_auth_token_ctx.get() == "outer-token"
    finally:
        veupathdb_auth_token_ctx.reset(reset)
