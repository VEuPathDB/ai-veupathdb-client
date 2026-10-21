"""Async HTTP client for one site's JBrowse service."""

from __future__ import annotations

import asyncio
from typing import Literal

import httpx

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import SiteNotFoundError, WDKLoginRequiredError
from veupathdb.guest_token import Credential, guest_tokens
from veupathdb.jbrowse.errors import JBrowseError
from veupathdb.jbrowse.models import TrackList
from veupathdb.settings import user_agent_header
from veupathdb.wdk.factory import list_sites

type TrackKind = Literal["organismSpecific", "rnaseq", "rnaseqJunctions"]

_GET = "GET"
_PARTIAL_CONTENT = 206
_UNAUTHORIZED = 401


class JBrowseClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        async with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=httpx.Timeout(self.timeout),
                    transport=self._transport,
                    headers=user_agent_header(),
                )
            return self._client

    def _service_url(self) -> str:
        sites = list_sites()
        for site in sites:
            if site.web_base_url == self.base_url:
                return site.service_url
        raise SiteNotFoundError(self.base_url, [site.id for site in sites])

    async def _credential(self) -> Credential:
        token = veupathdb_auth_token_ctx.get()
        if token:
            return Credential(token)
        return Credential(await guest_tokens().token(self._service_url()), guest=True)

    async def _get(
        self, path: str, params: dict[str, str] | None, headers: dict[str, str]
    ) -> httpx.Response:
        client = await self._http()
        credential = await self._credential()

        def build(token: str) -> httpx.Request:
            return client.build_request(
                _GET,
                path,
                params=params,
                headers={**headers, "Cookie": f"Authorization={token}"},
            )

        response = await client.send(build(credential.token))
        if credential.guest and response.status_code == _UNAUTHORIZED:
            renewed = await guest_tokens().renew(credential.token, self._service_url())
            response = await client.send(build(renewed))
            if response.status_code == _UNAUTHORIZED:
                raise WDKLoginRequiredError
        if not response.is_success:
            raise JBrowseError(_GET, str(response.request.url), response.status_code)
        return response

    async def track_list(self, kind: TrackKind, abbrev: str) -> TrackList:
        response = await self._get(
            f"/service/jbrowse/{kind}/{abbrev}", None, {"Accept": "application/json"}
        )
        return TrackList.model_validate_json(response.content)

    async def store_bytes(
        self, data_path: str, byte_range: tuple[int, int] | None = None
    ) -> bytes:
        headers = (
            {}
            if byte_range is None
            else {"Range": f"bytes={byte_range[0]}-{byte_range[1]}"}
        )
        response = await self._get(
            "/service/jbrowse/store", {"data": data_path}, headers
        )
        if byte_range is not None and response.status_code != _PARTIAL_CONTENT:
            raise JBrowseError(_GET, str(response.request.url), response.status_code)
        return response.content
