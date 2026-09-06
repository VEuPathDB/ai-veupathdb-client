"""The WDK transport: session identity, auth cookies, and what may be retried.

One client per site serves every task, so the clients share a cookie jar. The
global service account may not act on a user's WDK resources, and a create is
attempted once because a second attempt is a second object.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import (
    VEuPathDBError,
    VEuPathDBErrorCode,
    WDKLoginRequiredError,
)
from veupathdb.wdk._http import HTTPClient, _inject_auth_cookie
from veupathdb.wdk.delayed_result import DELAYED_RESULT_MESSAGE

SERVICE_ACCOUNT = "service.account.token"
USER_TOKEN = "registered.user.token"
_TOKEN_CTX = "veupathdb.wdk._http.veupathdb_auth_token_ctx"


async def _client(
    transport: httpx.AsyncBaseTransport,
    *,
    auth_token: str | None = None,
    base_url: str = "https://example.invalid/service",
) -> HTTPClient:
    """A client whose transport answers without reaching WDK."""
    client = HTTPClient(base_url=base_url, auth_token=auth_token)
    async with client._client_lock:
        client._client = httpx.AsyncClient(
            base_url=client.base_url, transport=transport, follow_redirects=True
        )
    return client


@pytest.fixture
def no_request_token() -> Generator[None]:
    reset = veupathdb_auth_token_ctx.set(None)
    yield
    veupathdb_auth_token_ctx.reset(reset)


class _ConstCtx:
    """A read-only stand-in for the auth token context variable."""

    def __init__(self, value: str | None) -> None:
        self._value = value

    def get(self) -> str | None:
        return self._value

    def set(self, *_: Any, **__: Any) -> Any:
        msg = "test-only ctxvar stub; use monkeypatch to swap"
        raise NotImplementedError(msg)


class _CapturingTransport(httpx.AsyncBaseTransport):
    """Answers 200 and records every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            200, json={}, headers={"content-type": "application/json"}
        )


class _RecordingTransport(httpx.AsyncBaseTransport):
    """Answers every request with 200 and remembers the paths it saw."""

    def __init__(self) -> None:
        self.paths: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        return httpx.Response(
            200, json={"id": 1}, headers={"content-type": "application/json"}
        )


class _FlakyTransport(httpx.AsyncBaseTransport):
    """Answers 502 until `fail_times` is exhausted, then 200."""

    def __init__(self, fail_times: int, body: object = None) -> None:
        self.fail_times = fail_times
        self.attempts = 0
        self._body = body if body is not None else {"id": 1}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/app"):
            # The WDK session bootstrap, not the request under test.
            return httpx.Response(200, text="ok")
        self.attempts += 1
        if self.attempts <= self.fail_times:
            return httpx.Response(502, text="Bad Gateway")
        return httpx.Response(
            200, json=self._body, headers={"content-type": "application/json"}
        )


def _cookie_pairs(request: httpx.Request) -> list[str]:
    header = request.headers.get("cookie", "")
    return [p.strip() for p in header.split(";") if p.strip()]


class TestThePerRequestAuthorizationCookieWins:
    """WDK sets an ``Authorization`` cookie on every response and the shared jar
    stores it. Two pairs of that name go out and the server reads the first.
    """

    def test_replaces_jar_authorization_cookie(self) -> None:
        request = httpx.Request(
            "GET",
            "https://plasmodb.org/plasmo/service/users/current",
            headers={"cookie": "Authorization=stale-jar-guest; JSESSIONID=abc123"},
        )
        _inject_auth_cookie(request, "real-user-token")
        pairs = _cookie_pairs(request)
        assert "Authorization=real-user-token" in pairs
        assert "JSESSIONID=abc123" in pairs
        auth_pairs = [p for p in pairs if p.startswith("Authorization=")]
        assert auth_pairs == ["Authorization=real-user-token"]

    def test_appends_when_no_authorization_present(self) -> None:
        request = httpx.Request(
            "GET",
            "https://plasmodb.org/plasmo/service/users/current",
            headers={"cookie": "JSESSIONID=abc123"},
        )
        _inject_auth_cookie(request, "real-user-token")
        pairs = _cookie_pairs(request)
        assert pairs == ["JSESSIONID=abc123", "Authorization=real-user-token"]

    def test_sets_cookie_header_when_absent(self) -> None:
        request = httpx.Request(
            "GET", "https://plasmodb.org/plasmo/service/users/current"
        )
        _inject_auth_cookie(request, "real-user-token")
        assert _cookie_pairs(request) == ["Authorization=real-user-token"]


class TestANewTokenStartsANewWdkSession:
    async def _ping(self, client: HTTPClient) -> None:
        await client._request_attempt("GET", "/ping", client._effective_token("/ping"))

    async def test_reinits_when_token_changes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two tokens on one client produce two session init calls."""
        transport = _CapturingTransport()
        client = await _client(
            transport, base_url="https://plasmodb.org/plasmo/service"
        )

        monkeypatch.setattr(_TOKEN_CTX, _ConstCtx("token-A"))
        await self._ping(client)
        monkeypatch.setattr(_TOKEN_CTX, _ConstCtx("token-B"))
        await self._ping(client)

        init_paths = [r for r in transport.requests if "/app" in str(r.url)]
        assert len(init_paths) == 2, (
            f"Expected 2 JSESSIONID init calls (one per token), "
            f"got {len(init_paths)}: {[str(r.url) for r in transport.requests]}"
        )

    async def test_does_not_reinit_when_token_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One token produces one session init call."""
        transport = _CapturingTransport()
        client = await _client(
            transport, base_url="https://plasmodb.org/plasmo/service"
        )

        monkeypatch.setattr(_TOKEN_CTX, _ConstCtx("token-same"))
        await self._ping(client)
        await self._ping(client)

        init_paths = [r for r in transport.requests if "/app" in str(r.url)]
        assert len(init_paths) == 1, (
            f"Expected 1 JSESSIONID init call, got {len(init_paths)}"
        )

    async def test_clears_jsessionid_cookie_on_reinit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A new session removes the session cookie of the previous token."""
        transport = _CapturingTransport()
        client = await _client(
            transport, base_url="https://plasmodb.org/plasmo/service"
        )
        client._client.cookies.set(
            "JSESSIONID", "stale-session-A", domain="plasmodb.org"
        )

        monkeypatch.setattr(_TOKEN_CTX, _ConstCtx("token-B"))
        await self._ping(client)

        assert client._client.cookies.get("JSESSIONID") != "stale-session-A", (
            "JSESSIONID from the previous token must not leak into the new "
            "token's request chain. Either the jar should be cleared or "
            "_init_wdk_session should replace the cookie entirely."
        )


@pytest.mark.usefixtures("no_request_token")
class TestAUserResourceNeedsTheUsersOwnToken:
    async def test_a_step_read_is_refused_and_never_leaves(self) -> None:
        transport = _RecordingTransport()
        client = await _client(transport, auth_token=SERVICE_ACCOUNT)

        with pytest.raises(WDKLoginRequiredError) as raised:
            await client.get("/users/1248677203/steps/9")

        assert raised.value.code == VEuPathDBErrorCode.WDK_LOGIN_REQUIRED
        assert raised.value.status == 401
        assert transport.paths == []

    async def test_a_step_create_is_refused(self) -> None:
        transport = _RecordingTransport()
        client = await _client(transport, auth_token=SERVICE_ACCOUNT)

        with pytest.raises(WDKLoginRequiredError):
            await client.post("/users/1248677203/steps", json={}, idempotent=False)

        assert transport.paths == []

    async def test_the_identity_probe_is_refused_too(self) -> None:
        """``/users/current`` resolves a WDK account, so it needs one."""
        transport = _RecordingTransport()
        client = await _client(transport, auth_token=SERVICE_ACCOUNT)

        with pytest.raises(WDKLoginRequiredError):
            await client.get("/users/current")

        assert transport.paths == []

    async def test_the_users_own_token_is_served(self) -> None:
        transport = _RecordingTransport()
        client = await _client(transport, auth_token=SERVICE_ACCOUNT)
        veupathdb_auth_token_ctx.set(USER_TOKEN)

        assert await client.get("/users/1248677203/steps/9") == {"id": 1}
        assert "/service/users/1248677203/steps/9" in transport.paths


@pytest.mark.usefixtures("no_request_token")
class TestUserIndependentReadsStillRunAsTheApplication:
    async def test_a_search_listing_is_served(self) -> None:
        transport = _RecordingTransport()
        client = await _client(transport, auth_token=SERVICE_ACCOUNT)

        assert await client.get("/record-types/transcript/searches") == {"id": 1}
        assert "/service/record-types/transcript/searches" in transport.paths

    async def test_a_search_detail_read_is_served(self) -> None:
        transport = _RecordingTransport()
        client = await _client(transport, auth_token=SERVICE_ACCOUNT)

        assert await client.get("/record-types/transcript/searches/GenesByText") == {
            "id": 1
        }


@pytest.mark.usefixtures("wdk_request_token")
class TestACreateIsAttemptedOnce:
    """A proxy answers 502 after passing the request upstream, so a retried
    ``POST /steps`` leaves a step nobody references.
    """

    async def test_a_step_create_is_not_retried(self) -> None:
        transport = _FlakyTransport(fail_times=2)
        client = await _client(transport)

        with pytest.raises(VEuPathDBError):
            await client.post("/users/1/steps", json={}, idempotent=False)

        assert transport.attempts == 1

    async def test_a_successful_create_still_returns(self) -> None:
        transport = _FlakyTransport(fail_times=0)
        client = await _client(transport)

        assert await client.post("/users/1/steps", json={}, idempotent=False) == {
            "id": 1
        }


@pytest.mark.usefixtures("wdk_request_token")
class TestReadsAreStillRetried:
    async def test_a_get_recovers_from_a_proxy_error(self) -> None:
        transport = _FlakyTransport(fail_times=2)
        client = await _client(transport)

        assert await client.get("/users/1/steps/9") == {"id": 1}
        assert transport.attempts == 3

    async def test_a_report_post_is_retried_by_default(self) -> None:
        # A report POST is a read with a body, and the delayed-result guard
        # depends on it being retried.
        transport = _FlakyTransport(fail_times=2)
        client = await _client(transport)

        await client.post("/users/1/steps/9/reports/standard", json={})

        assert transport.attempts == 3


@pytest.mark.usefixtures("wdk_request_token")
class TestTheDelayedResultGuardStillRetries:
    async def test_the_sentinel_is_retried_on_a_report(self) -> None:
        class _Sentinel(httpx.AsyncBaseTransport):
            def __init__(self) -> None:
                self.attempts = 0

            async def handle_async_request(
                self, request: httpx.Request
            ) -> httpx.Response:
                del request
                self.attempts += 1
                body = (
                    {"status": "accepted", "message": DELAYED_RESULT_MESSAGE}
                    if self.attempts == 1
                    else {"id": 1}
                )
                return httpx.Response(
                    200, json=body, headers={"content-type": "application/json"}
                )

        transport = _Sentinel()
        client = await _client(transport)

        assert await client.post("/users/1/steps/9/reports/standard", json={}) == {
            "id": 1
        }
        assert transport.attempts == 2
