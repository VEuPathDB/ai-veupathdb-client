"""Reading ``GET /users/current``: the typed profile and the registered email."""

from __future__ import annotations

import httpx
import respx

from veupathdb.auth_context import veupathdb_auth_token_ctx
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
async def test_a_refused_read_names_nobody() -> None:
    _allow_session_init()
    respx.get(_CURRENT_USER).mock(return_value=httpx.Response(503, text="down"))
    reset = veupathdb_auth_token_ctx.set("a-token")
    try:
        assert await fetch_current_user("plasmodb") is None
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
        assert await resolve_registered_email("inner-token", "plasmodb") is None
        assert veupathdb_auth_token_ctx.get() == "outer-token"
    finally:
        veupathdb_auth_token_ctx.reset(reset)
