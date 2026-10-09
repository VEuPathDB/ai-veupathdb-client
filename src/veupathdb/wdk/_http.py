"""Core HTTP transport for VEuPathDB WDK REST API with retries and cookies."""

import asyncio
import re
import time
from collections.abc import Mapping, Sequence
from typing import cast
from urllib.parse import urlparse

import httpx
from pydantic import JsonValue
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from veupathdb.auth_context import (
    resolve_veupathdb_auth_token,
    veupathdb_auth_token_ctx,
)
from veupathdb.errors import WDKError, WDKLoginRequiredError
from veupathdb.json_types import JSONObject
from veupathdb.logging import get_logger
from veupathdb.observer import get_observer
from veupathdb.settings import DEFAULT_CONCURRENT_SEARCHES_PER_SITE, user_agent_header
from veupathdb.wdk._failures import wdk_failure
from veupathdb.wdk._observability import (
    WdkRequestTelemetry,
    wdk_retry_logger,
)
from veupathdb.wdk._search_names import SearchNames, search_kind
from veupathdb.wdk.delayed_result import (
    WDKDelayedResultError,
    is_delayed_result,
)
from veupathdb.wdk.probe import WDKProbe
from veupathdb.wdk.search_load import (
    SearchRequest,
    in_turn_line,
    search_gate,
    waited_for,
)

logger = get_logger(__name__)

_HTTP_SERVER_ERROR = 500
_MAX_CONNECTIONS = 64
_MAX_KEEPALIVE_CONNECTIONS = 16
_ATTEMPTS = 3
_RETRYABLE = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.HTTPStatusError,
    WDKDelayedResultError,
)
_SEARCH_RETRYABLE = (httpx.ConnectError, WDKDelayedResultError)

# Steps, strategies, datasets, baskets, favorites and preferences all hang off
# a user, and ``/users/current`` resolves which user that is.
_USER_PATH = re.compile(r"^/users/")


def _acts_for_a_user(path: str) -> bool:
    """True when the path names a WDK account or something inside one."""
    return bool(_USER_PATH.match(path))


_REPORT = re.compile(r"/reports/[^/]+$")
_ANALYSIS_RUN = re.compile(r"/analyses/[^/]+/result$")
_ANSWERED_RESOURCE = re.compile(r"^/users/[^/]+/(?:steps|strategies)/[^/]+$")


def runs_a_search(method: str, path: str) -> bool:
    if _REPORT.search(path):
        return True
    if method == "POST":
        return bool(_ANALYSIS_RUN.search(path))
    return method == "GET" and bool(_ANSWERED_RESOURCE.match(path))


def _cause(error: BaseException | None) -> str:
    """The error's text, or its class name when the text is empty."""
    return str(error) or type(error).__name__


def _inject_auth_cookie(request: httpx.Request, auth_token: str) -> None:
    """Set the ``Authorization`` cookie on a built request, replacing any jar value.

    Only the per-request object changes, so concurrent requests with different
    tokens stay independent. Tomcat honors the first of two ``Authorization``
    pairs, so the jar value must be removed and not appended to.
    """
    existing = request.headers.get("cookie", "")
    kept = [
        pair.strip()
        for pair in existing.split(";")
        if pair.strip() and not pair.strip().startswith("Authorization=")
    ]
    kept.append(f"Authorization={auth_token}")
    request.headers["cookie"] = "; ".join(kept)


def _convert_params_for_httpx(
    params: JSONObject | None,
) -> (
    Mapping[
        str, str | int | float | bool | Sequence[str | int | float | bool | None] | None
    ]
    | None
):
    """Convert JSON params into the mapping shape that httpx accepts."""
    if params is None:
        return None
    result: dict[
        str, str | int | float | bool | Sequence[str | int | float | bool | None] | None
    ] = {}
    for k, v in params.items():
        if v is None:
            result[k] = None
        elif isinstance(v, (str, int, float, bool)):
            result[k] = v
        elif isinstance(v, list):
            converted_list: list[str | int | float | bool | None] = []
            for item in v:
                if isinstance(item, (str, int, float, bool)) or item is None:
                    converted_list.append(item)
                else:
                    converted_list.append(str(item))
            result[k] = converted_list
        else:
            result[k] = str(v)
    return result


class HTTPClient:
    """Low-level HTTP transport for VEuPathDB WDK REST services."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        auth_token: str | None = None,
        *,
        concurrent_searches: int = DEFAULT_CONCURRENT_SEARCHES_PER_SITE,
        site_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.site_id = site_id or urlparse(self.base_url).hostname or self.base_url
        self.timeout = timeout
        self.auth_token = auth_token
        self.concurrent_searches = concurrent_searches
        self._search_slots = asyncio.Semaphore(concurrent_searches)
        self._search_names = SearchNames()
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()
        # The JSESSIONID cookie in the shared jar is scoped to one identity.
        # A change of token requires a new session.
        self._initialized_for_token: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the shared HTTP client, creating it on first use."""
        if self._client is not None and not self._client.is_closed:
            return self._client
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=httpx.Timeout(self.timeout),
                    follow_redirects=True,
                    limits=httpx.Limits(
                        max_connections=_MAX_CONNECTIONS,
                        max_keepalive_connections=_MAX_KEEPALIVE_CONNECTIONS,
                    ),
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        **user_agent_header(),
                    },
                )
            return self._client

    async def _init_wdk_session(
        self, client: httpx.AsyncClient, auth_token: str
    ) -> None:
        """Establish a server-side WDK session through the webapp.

        WDK process queries need a Tomcat ``JSESSIONID``. Without one they
        return zero results and no error.
        """
        webapp_url = self.base_url.replace("/service", "/app")
        try:
            request = client.build_request("GET", webapp_url, timeout=10)
            _inject_auth_cookie(request, auth_token)
            await client.send(request)
            logger.debug(
                "WDK session initialized",
                jsessionid=bool(client.cookies.get("JSESSIONID")),
            )
        except httpx.HTTPError, OSError, RuntimeError:
            logger.debug("Failed to initialize WDK session (non-fatal)")

    def _effective_token(self, path: str) -> str | None:
        """Resolve the token one request travels with.

        Only the request's own token may reach a WDK account.
        """
        if _acts_for_a_user(path) and not veupathdb_auth_token_ctx.get():
            raise WDKLoginRequiredError
        return resolve_veupathdb_auth_token(self.auth_token)

    async def close(self) -> None:
        """Close the HTTP client and clear session state.

        The JSESSIONID lives on the client cookie jar, so a new client must
        establish a new WDK session.
        """
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        self._initialized_for_token = None

    async def _request_attempt(
        self,
        method: str,
        path: str,
        auth_token: str | None,
        params: JSONObject | None = None,
        json: object = None,
        budget_seconds: float | None = None,
    ) -> JsonValue:
        """Make one HTTP request attempt. Tenacity drives the retries."""
        client = await self._get_client()
        telemetry = WdkRequestTelemetry(
            method=method,
            path=path,
            base_url=self.base_url,
            has_auth=bool(auth_token),
        )

        logger.debug(
            "VEuPathDB request",
            method=method,
            path=path,
            base_url=self.base_url,
            endpoint_group=telemetry.metric_attrs(outcome="pending")["endpoint_group"],
        )

        try:
            # WDK authenticates through an Authorization cookie, not a header.
            if auth_token and auth_token != self._initialized_for_token:
                # A JSESSIONID belongs to one identity and must not be reused.
                client.cookies.delete("JSESSIONID")
                self._initialized_for_token = auth_token
                await self._init_wdk_session(client, auth_token)
            httpx_params = _convert_params_for_httpx(params)
            request = client.build_request(
                method=method,
                url=path,
                params=httpx_params,
                json=json,
            )
            if auth_token:
                _inject_auth_cookie(request, auth_token)
            async with asyncio.timeout(budget_seconds):
                response = await client.send(request)
            response.raise_for_status()
            if not response.content or not response.text.strip():
                return None
            result = response.json()
            if result is None:
                return None
            if is_delayed_result(result):
                # WDK sends this with a 2xx, so only the body identifies it.
                raise WDKDelayedResultError
            return cast("JsonValue", result)
        except httpx.HTTPStatusError as e:
            allow = e.response.headers.get("allow") or e.response.headers.get("Allow")
            log_fn = (
                logger.warning
                if e.response.status_code >= _HTTP_SERVER_ERROR
                else logger.error
            )
            log_fn(
                "VEuPathDB HTTP error",
                method=method,
                status_code=e.response.status_code,
                path=path,
                allow=allow,
                response_text=e.response.text[:500],
            )
            # 5xx is retryable. 4xx is not.
            if e.response.status_code >= _HTTP_SERVER_ERROR:
                raise
            raise wdk_failure(
                method, path, e.response.status_code, e.response.text
            ) from e
        except httpx.TimeoutException, httpx.ConnectError:
            # Transient. Tenacity retries these.
            raise
        except httpx.RequestError as e:
            logger.exception("VEuPathDB request error", error=_cause(e), path=path)
            msg = f"Request failed: {_cause(e)}"
            raise WDKError(msg, status=502) from e

    @staticmethod
    def _retrying(
        *, attempts: int, telemetry: WdkRequestTelemetry, searching: bool
    ) -> AsyncRetrying:
        """The retry policy for one request.

        A non-idempotent request gets a single attempt: a proxy 502 can follow a
        write WDK already committed, and a second attempt is a second object.
        """
        return AsyncRetrying(
            retry=retry_if_exception_type(
                _SEARCH_RETRYABLE if searching else _RETRYABLE
            ),
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            before_sleep=wdk_retry_logger(telemetry),
            reraise=False,
        )

    async def _search_attempt(
        self,
        method: str,
        path: str,
        auth_token: str | None,
        params: JSONObject | None = None,
        json: object = None,
        budget_seconds: float | None = None,
    ) -> JsonValue:
        request = SearchRequest(
            site_id=self.site_id,
            kind=search_kind(path),
            search_names=self._search_names.of(path),
        )
        async with (
            in_turn_line(self.site_id),
            search_gate()(request),
            waited_for(self.site_id, "site", self._search_slots),
        ):
            return await self._request_attempt(
                method,
                path,
                auth_token,
                params=params,
                json=json,
                budget_seconds=budget_seconds,
            )

    def _failed(
        self,
        last: BaseException | None,
        telemetry: WdkRequestTelemetry,
        start: float,
        method: str,
        path: str,
    ) -> WDKError:
        status_code = None
        if isinstance(last, httpx.HTTPStatusError):
            status_code = last.response.status_code
        metric_attrs = telemetry.metric_attrs(
            outcome="error",
            status_code=status_code,
        )
        get_observer().on_wdk_request(time.monotonic() - start, metric_attrs)
        status = 502 if status_code is None else status_code
        log_fn = logger.warning if status >= _HTTP_SERVER_ERROR else logger.error
        log_fn(
            "VEuPathDB request failed after retries",
            method=method,
            path=path,
            endpoint_group=metric_attrs["endpoint_group"],
            site_host=metric_attrs["site_host"],
            error=_cause(last),
        )
        msg = f"Request failed after retries: {_cause(last)}"
        return WDKError(msg, status=status)

    async def _request(
        self,
        method: str,
        path: str,
        params: JSONObject | None = None,
        json: object = None,
        *,
        attempts: int = _ATTEMPTS,
        budget_seconds: float | None = None,
    ) -> JsonValue:
        """Make an HTTP request with retries, and record telemetry."""
        start = time.monotonic()
        auth_token = self._effective_token(path)
        searching = runs_a_search(method, path)
        telemetry = WdkRequestTelemetry(
            method=method,
            path=path,
            base_url=self.base_url,
            has_auth=bool(auth_token),
        )
        try:
            result: JsonValue = await self._retrying(
                attempts=attempts,
                telemetry=telemetry,
                searching=searching,
            )(
                self._search_attempt if searching else self._request_attempt,
                method,
                path,
                auth_token,
                params=params,
                json=json,
                budget_seconds=budget_seconds,
            )
        except RetryError as e:
            last = e.last_attempt.exception()
            raise self._failed(last, telemetry, start, method, path) from last
        except (httpx.HTTPStatusError, httpx.TimeoutException) as last:
            raise self._failed(last, telemetry, start, method, path) from last
        except WDKError as error:
            metric_attrs = telemetry.metric_attrs(
                outcome="error",
                status_code=error.status,
            )
            get_observer().on_wdk_request(time.monotonic() - start, metric_attrs)
            raise
        else:
            metric_attrs = telemetry.metric_attrs(outcome="ok", status_code=200)
            get_observer().on_wdk_request(time.monotonic() - start, metric_attrs)
            self._search_names.learn(method, path, json, result)
            return result

    async def probe(
        self,
        method: str,
        path: str,
        params: JSONObject | None = None,
        json: object = None,
    ) -> WDKProbe:
        """Send one request and report what WDK answered, without retrying.

        A 4xx is the measurement, so nothing here raises on one.
        """
        client = await self._get_client()
        auth_token = self._effective_token(path)
        request = client.build_request(
            method=method,
            url=path,
            params=_convert_params_for_httpx(params),
            json=json,
        )
        if auth_token:
            _inject_auth_cookie(request, auth_token)
        response = await client.send(request)
        return WDKProbe(
            method=method,
            url=str(response.request.url),
            status=response.status_code,
            content_type=response.headers.get("content-type", ""),
            text=response.text,
        )

    async def get(
        self,
        path: str,
        params: JSONObject | None = None,
        *,
        attempts: int = _ATTEMPTS,
    ) -> JsonValue:
        """GET request. ``attempts`` bounds the retries of this one read."""
        return await self._request("GET", path, params=params, attempts=attempts)

    async def post(
        self,
        path: str,
        json: object = None,
        params: JSONObject | None = None,
        *,
        idempotent: bool = True,
        budget_seconds: float | None = None,
    ) -> JsonValue:
        """POST request.

        Pass ``idempotent=False`` for a create, so a proxy error is not retried
        into a second object.
        """
        return await self._request(
            "POST",
            path,
            params=params,
            json=json,
            attempts=_ATTEMPTS if idempotent else 1,
            budget_seconds=budget_seconds,
        )

    async def patch(self, path: str, json: object = None) -> JsonValue:
        """PATCH request."""
        return await self._request("PATCH", path, json=json)

    async def put(self, path: str, json: object = None) -> JsonValue:
        """PUT request."""
        return await self._request("PUT", path, json=json)

    async def delete(self, path: str) -> JsonValue:
        """DELETE request."""
        return await self._request("DELETE", path)
