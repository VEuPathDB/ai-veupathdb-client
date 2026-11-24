from __future__ import annotations

import asyncio
import contextlib
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veupathdb.guest_token import authorization_cookies
from veupathdb.testing.wire.drift import Compared, DriftRow, compare
from veupathdb.testing.wire.idmap import IdMap, UnmappedIdError
from veupathdb.testing.wire.key import FAKE_USER_ID
from veupathdb.testing.wire.models import (
    STACK,
    Cassette,
    CassetteHeader,
    Credential,
    Exchange,
    stored_body,
)
from veupathdb.testing.wire.redact import ACCOUNT_EMAIL, Identity, LeakError, Redactor
from veupathdb.testing.wire.store import WireStore
from veupathdb.wdk.auth_login import extract_auth_cookie

PARALLEL_CASSETTES = 4
_FAKE = re.compile(rf"(?<!\d){FAKE_USER_ID}(?!\d)")


class UnsafeRequestError(ValueError):
    pass


def _safe_path(path: str) -> str:
    unsafe = (
        not path.startswith("/")
        or any(mark in path for mark in ("@", "//", "://", "\\", "?", "#"))
        or ".." in path.split("/")
    )
    if unsafe:
        msg = f"{path!r} is not a plain service path"
        raise UnsafeRequestError(msg)
    return path


class _User(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    email: str = ""
    isGuest: bool = True
    properties: dict[str, str] = Field(default_factory=dict)


class _Root(BaseModel):
    model_config = ConfigDict(extra="ignore")

    buildNumber: int


class Answer(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: int
    content_type: str
    set_cookies: list[str]
    body: bytes
    ms: float


class WdkSession:
    def __init__(self, services: dict[str, str], client: httpx.AsyncClient) -> None:
        self.services = services
        self.client = client
        self.secrets: set[str] = set()
        self.builds: dict[str, int] = {}
        self._registered = ""
        self._guest = ""

    async def sign_in(self, email: str, password: str, host: str) -> Identity:
        service = self.services[host]
        login = await self.client.post(
            f"{service}/login",
            json={"email": email, "password": password, "redirectUrl": "/"},
        )
        token = extract_auth_cookie(login.headers.get_list("set-cookie"))
        if token is None:
            msg = f"the {host} login refused the test account ({login.status_code})"
            raise PermissionError(msg)
        self._registered = token
        self.secrets |= {token, password}
        current = await self._get(f"{service}/users/current", token)
        user = _User.model_validate_json(current.content)
        return Identity(
            user_id=user.id,
            email=user.email,
            first_name=user.properties.get("firstName", ""),
            last_name=user.properties.get("lastName", ""),
            organization=user.properties.get("organization", ""),
        )

    async def _get(self, url: str, token: str = "") -> httpx.Response:
        return await self.request("GET", url, token)

    async def request(
        self, method: str, url: httpx.URL | str, token: str = ""
    ) -> httpx.Response:
        headers = {"cookie": f"Authorization={token}"} if token else {}
        response = await self.client.request(method, url, headers=headers)
        self.client.cookies.clear()
        return response

    def url(self, host: str, path: str) -> httpx.URL:
        service = self.services.get(host)
        if service is None:
            msg = f"{host} is not a configured service"
            raise UnsafeRequestError(msg)
        origin = httpx.URL(service)
        url = httpx.URL(
            scheme=origin.scheme,
            host=origin.host,
            port=origin.port,
            path=_safe_path(path),
        )
        if url.path != path or url.query or url.fragment or url.host != host:
            msg = f"{path!r} does not parse back as itself on {host}"
            raise UnsafeRequestError(msg)
        return url

    async def sweep(self, host: str, path: str) -> None:
        await self.request("DELETE", self.url(host, path), self._registered)

    async def read_builds(self) -> None:
        for host, service in self.services.items():
            self._note_build(host, (await self._get(service)).content)

    def _note_build(self, host: str, content: bytes) -> None:
        with contextlib.suppress(ValidationError):
            self.builds[host] = _Root.model_validate_json(content).buildNumber

    async def _guest_token(self, host: str) -> str:
        if not self._guest:
            minted = await self._get(self.services[host])
            tokens = authorization_cookies(minted.headers.get_list("set-cookie"))
            self._guest = tokens[0] if tokens else ""
            self.secrets.add(self._guest)
        return self._guest

    async def send(
        self, exchange: Exchange, url: httpx.URL, body: bytes, credential: Credential
    ) -> Answer:
        token = ""
        if credential == "registered":
            token = self._registered
        elif credential == "guest":
            token = await self._guest_token(exchange.host)
        headers = {"cookie": f"Authorization={token}"} if token else {}
        if body:
            headers["content-type"] = "application/json"
        query: list[tuple[str, str | int | float | bool | None]] = list(exchange.query)
        started = time.monotonic()
        response = await self.client.request(
            exchange.method,
            url,
            params=query,
            content=body or None,
            headers=headers,
        )
        self.client.cookies.clear()
        set_cookies = response.headers.get_list("set-cookie")
        self.secrets.update(c.split(";", 1)[0].partition("=")[2] for c in set_cookies)
        self._note_build(exchange.host, response.content)
        return Answer(
            status=response.status_code,
            content_type=response.headers.get("content-type", ""),
            set_cookies=[c.split("=", 1)[0].strip() for c in set_cookies],
            body=response.content,
            ms=round(1000 * (time.monotonic() - started), 1),
        )


class RefreshResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    rows: list[DriftRow]
    errors: list[str]
    builds: dict[str, tuple[int | None, int | None]]


class _Refreshed(BaseModel):
    model_config = ConfigDict(frozen=True)

    cassette: Cassette | None
    row: DriftRow
    error: str = ""


class _Run:
    def __init__(
        self, store: WireStore, session: WdkSession, identity: Identity
    ) -> None:
        self.store = store
        self.session = session
        self.identity = identity

    def _real(self, text: str) -> str:
        text = _FAKE.sub(str(self.identity.user_id), text)
        return text.replace(ACCOUNT_EMAIL, self.identity.email)

    async def one(self, cassette: Cassette) -> _Refreshed:
        name = cassette.header.cassette
        ids = IdMap(self.identity.user_id)
        sent: list[tuple[Exchange, Answer, bytes]] = []
        compared: list[Compared] = []
        try:
            for exchange in sorted(cassette.exchanges, key=lambda e: e.seq):
                path = ids.rewrite_path(self._real(exchange.path))
                body = exchange.request_bytes()
                if not exchange.body_base64:
                    body = (
                        ids.rewrite_body(self._real(body.decode())).encode()
                        if body
                        else b""
                    )
                query = ids.rewrite_query(exchange.query)
                url = self.session.url(exchange.host, path)
                path = url.path
                ids.check(
                    exchange.method,
                    path,
                    query,
                    body.decode(errors="replace") if body else None,
                )
                answer = await self.session.send(
                    exchange.model_copy(update={"query": query}),
                    url,
                    body,
                    exchange.credential,
                )
                old = (
                    self.store.read_body(exchange.response)
                    if exchange.response
                    else b""
                )
                rewritten = exchange.model_copy(update={"path": path, "query": query})
                ids.learn(rewritten, old, answer.body)
                if exchange.method == "DELETE":
                    ids.forget(path)
                sent.append((rewritten, answer, body))
                compared.append(
                    (
                        f"{exchange.method} {exchange.path}",
                        exchange.status,
                        answer.status,
                        old,
                        answer.body,
                    )
                )
        except (UnmappedIdError, UnsafeRequestError, httpx.HTTPError) as error:
            failure = f"{name}: {error}"
        else:
            failure = ""
        failure = "; ".join(filter(None, [failure, *await self._sweep(ids)]))
        if failure:
            return _Refreshed(cassette=None, row=DriftRow(cassette=name), error=failure)
        return self._written(cassette, sent, compared)

    async def _sweep(self, ids: IdMap) -> list[str]:
        failures = []
        for host, leftover in ids.sweep_paths():
            try:
                await self.session.sweep(host, leftover)
            except (UnsafeRequestError, httpx.HTTPError) as error:
                failures.append(f"the sweep of {leftover} failed: {error}")
        return failures

    def _written(
        self,
        cassette: Cassette,
        sent: list[tuple[Exchange, Answer, bytes]],
        compared: list[Compared],
    ) -> _Refreshed:
        name = cassette.header.cassette
        redactor = Redactor(self.identity, self.session.secrets)
        guarded = WireStore(self.store.root, guard=redactor)
        redacted = [
            (label, old_status, new_status, old, redactor.body(new))
            for label, old_status, new_status, old, new in compared
        ]
        try:
            exchanges = []
            for exchange, answer, body in sent:
                text, base64 = stored_body(redactor.body(body))
                exchanges.append(
                    exchange.model_copy(
                        update={
                            "path": redactor.path(exchange.path),
                            "body": text,
                            "body_base64": base64,
                            "status": answer.status,
                            "content_type": answer.content_type,
                            "set_cookies": answer.set_cookies,
                            "response": guarded.put_body(redactor.body(answer.body))
                            if answer.body
                            else None,
                            "ms": answer.ms,
                        }
                    )
                )
            hosts = {exchange.host for exchange in exchanges}
            refreshed = Cassette(
                header=CassetteHeader(
                    cassette=name,
                    recorded_at=datetime.now(UTC),
                    builds={h: b for h, b in self.session.builds.items() if h in hosts},
                ),
                exchanges=exchanges,
            )
            guarded.write_cassette(refreshed)
        except LeakError as error:
            return _Refreshed(
                cassette=None, row=DriftRow(cassette=name), error=f"{name}: {error}"
            )
        return _Refreshed(cassette=refreshed, row=compare(name, redacted))


async def refresh(
    root: Path,
    session: WdkSession,
    email: str,
    password: str,
    login_host: str,
    *,
    parallel: int = PARALLEL_CASSETTES,
) -> RefreshResult:
    store = WireStore(root)
    before = store.read_manifest()
    identity = await session.sign_in(email, password, login_host)
    await session.read_builds()
    run = _Run(store, session, identity)
    stack = store.read_cassette(STACK)
    results = [await run.one(stack)] if stack else []
    gate = asyncio.Semaphore(parallel)

    async def guarded(cassette_id: str) -> _Refreshed:
        cassette = store.read_cassette(cassette_id)
        if cassette is None:
            msg = f"{cassette_id} vanished during the refresh"
            raise FileNotFoundError(msg)
        async with gate:
            return await run.one(cassette)

    results += await asyncio.gather(*(guarded(c) for c in store.cassette_ids()))
    store.prune_bodies()
    after = store.write_manifest()
    hosts = before.hosts.keys() | after.hosts.keys()
    builds = {
        host: (
            max(before.hosts[host].builds) if host in before.hosts else None,
            max(after.hosts[host].builds) if host in after.hosts else None,
        )
        for host in hosts
    }
    return RefreshResult(
        rows=[
            r.row
            for r in results
            if r.cassette is not None and r.cassette.header.cassette != STACK
        ],
        errors=[r.error for r in results if r.error],
        builds=builds,
    )
