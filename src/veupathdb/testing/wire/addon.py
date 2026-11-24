from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from mitmproxy import http
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veupathdb.json_types import JSONObject
from veupathdb.settings import DEFAULT_OAUTH_URL
from veupathdb.testing.guest import HERMETIC_GUEST_TOKEN
from veupathdb.testing.wire.key import FAKE_USER_ID, exchange_key
from veupathdb.testing.wire.models import (
    STACK,
    Cassette,
    CassetteHeader,
    Credential,
    Exchange,
    stored_body,
)
from veupathdb.testing.wire.redact import (
    ACCOUNT_EMAIL,
    ACCOUNT_FIRST_NAME,
    ACCOUNT_LAST_NAME,
    ACCOUNT_ORGANIZATION,
    REDACTED,
    Identity,
    LeakError,
    Redactor,
)
from veupathdb.testing.wire.replay import (
    Miss,
    MissReason,
    Played,
    nearest_difference,
    render_misses,
)
from veupathdb.testing.wire.signing import SigningKey, token_claims
from veupathdb.testing.wire.stack import merge_stack
from veupathdb.testing.wire.store import WireStore
from veupathdb.wdk._http import changes_user_state
from veupathdb.wdk.site_router import load_sites_config

logger = logging.getLogger(__name__)

WireMode = Literal["replay", "record"]
OPENAI_HOST = "api.openai.com"
CONTROL = "/__wire/"
_OPENAI_REFUSAL: JSONObject = {
    "error": {
        "message": "Incorrect API key provided.",
        "type": "invalid_request_error",
        "code": "invalid_api_key",
    }
}
_CURRENT_USER = re.compile(r"/users/current$")
_JSON = {"content-type": "application/json"}


def cassette_email(cassette: str) -> str:
    digest = hashlib.sha256(cassette.encode()).hexdigest()[:12]
    return f"e2e+{digest}@strategist.test"


def site_hosts(sites_file: Path) -> frozenset[str]:
    config = load_sites_config(str(sites_file))
    hosts = (urlsplit(site.base_url).hostname for site in config.sites.values())
    return frozenset(host for host in hosts if host)


class _Begin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cassette: str


class _End(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cassette: str
    keep: bool = True


class _CurrentUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    email: str | None = None
    isGuest: bool = True
    properties: dict[str, str] = Field(default_factory=dict)


class _ServiceRoot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    buildNumber: int


class _Seen(BaseModel):
    model_config = ConfigDict(frozen=True)

    exchange: Exchange
    response: bytes


def _json(
    status: int, body: object, headers: dict[str, str] | None = None
) -> http.Response:
    return http.Response.make(
        status, json.dumps(body).encode(), {**_JSON, **(headers or {})}
    )


def _token(request: http.Request) -> str | None:
    bearer = request.headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        return bearer[len("bearer ") :].strip() or None
    return request.cookies.get("Authorization") or None


def _credential(token: str | None) -> Credential:
    if token is None:
        return "none"
    claims = token_claims(token)
    return "guest" if claims is None or claims.is_guest else "registered"


def _query(request: http.Request) -> list[tuple[str, str]]:
    return [(str(k), str(v)) for k, v in request.query.items(multi=True)]


class WireAddon:
    def __init__(
        self,
        mode: WireMode,
        store: WireStore,
        hosts: frozenset[str],
        *,
        oauth_url: str = DEFAULT_OAUTH_URL,
    ) -> None:
        self.mode = mode
        self.store = store
        self.hosts = hosts
        self.oauth_host = urlsplit(oauth_url).hostname or ""
        self.key = SigningKey.generate()
        self._played: dict[str, Played] = {}
        self._misses: dict[str, list[Miss]] = {}
        self._stack_misses: list[Miss] = []
        self._active: str | None = None
        self._recorded: dict[str, list[_Seen]] = {}
        self._writes: dict[str, int] = {}
        self._builds: dict[str, int] = {}
        self._identity: Identity | None = None
        self._secrets: set[str] = set()

    def _allowed(self, host: str) -> bool:
        return host in self.hosts or host in {self.oauth_host, OPENAI_HOST}

    def request(self, flow: http.HTTPFlow) -> None:
        request = flow.request
        host = request.pretty_host
        if request.path.startswith(CONTROL) and not self._allowed(host):
            flow.response = self._control(request)
            return
        if not self._allowed(host):
            self._refuse(flow, STACK, "host", self._stack_misses)
            return
        if self.mode == "record":
            self._note_secrets(request)
            return
        flow.response = self._answer(flow)

    def response(self, flow: http.HTTPFlow) -> None:
        if self.mode == "record" and flow.response is not None:
            self._record(flow, flow.response)

    def _control(self, request: http.Request) -> http.Response:
        route = (request.method, urlsplit(request.path).path)
        match route:
            case ("GET", "/__wire/health"):
                return _json(200, {"mode": self.mode})
            case ("GET", "/__wire/signing-key") if self.mode == "replay":
                return _json(200, self.key.private_jwk())
            case ("POST", "/__wire/begin"):
                return self._begin(_Begin.model_validate_json(request.content or b"{}"))
            case ("POST", "/__wire/end"):
                return self._end(_End.model_validate_json(request.content or b"{}"))
            case ("POST", "/__wire/finish"):
                return self._finish()
            case _:
                return _json(404, {"error": f"no wire route {route[0]} {route[1]}"})

    def _begin(self, begin: _Begin) -> http.Response:
        if self.mode == "record":
            self._active = begin.cassette
            self._recorded[begin.cassette] = []
            self._writes[begin.cassette] = 0
        else:
            self._played_for(begin.cassette).rewind()
            self._misses[begin.cassette] = []
        return _json(200, {"cassette": begin.cassette})

    def _end(self, end: _End) -> http.Response:
        if self.mode == "record":
            self._active = None
            if not end.keep:
                self._recorded.pop(end.cassette, None)
                return _json(200, {"written": False})
            try:
                self._write(end.cassette)
            except LeakError as error:
                return _json(500, {"error": str(error)})
            return _json(200, {"written": True})
        misses = self._misses.pop(end.cassette, [])
        unsent = self._played_for(end.cassette).unsent_writes()
        return _json(200, self._outcome(end.cassette, misses, unsent))

    def _finish(self) -> http.Response:
        if self.mode == "replay":
            return _json(200, self._outcome(STACK, self._stack_misses, []))
        try:
            self._write(STACK)
        except LeakError as error:
            return _json(500, {"error": str(error)})
        manifest = self.store.write_manifest()
        return _json(200, {"cassettes": manifest.cassettes})

    @staticmethod
    def _outcome(
        cassette: str, misses: list[Miss], unsent: list[Exchange]
    ) -> JSONObject:
        report = render_misses(cassette, misses, unsent) if misses or unsent else ""
        return {
            "misses": [miss.model_dump(mode="json") for miss in misses],
            "unsent": [exchange.model_dump(mode="json") for exchange in unsent],
            "report": report,
        }

    def _played_for(self, cassette: str) -> Played:
        played = self._played.get(cassette)
        if played is None:
            recorded = self.store.read_cassette(cassette) or Cassette(
                header=CassetteHeader(cassette=cassette, recorded_at=datetime.now(UTC))
            )
            played = self._played[cassette] = Played(recorded)
        return played

    def _refuse(
        self, flow: http.HTTPFlow, cassette: str, reason: MissReason, misses: list[Miss]
    ) -> None:
        request = flow.request
        path = urlsplit(request.path).path
        nearest: str = ""
        differences: list[str] = []
        if reason in {"unrecorded", "used-up"}:
            nearest, differences = nearest_difference(
                self._played_for(cassette).cassette,
                request.method,
                request.pretty_host,
                path,
                request.content or b"",
            )
        miss = Miss(
            cassette=cassette,
            method=request.method,
            host=request.pretty_host,
            path=path,
            reason=reason,
            body=(request.content or b"").decode("utf-8", errors="replace") or None,
            nearest=nearest,
            differences=differences,
        )
        misses.append(miss)
        logger.warning(render_misses(cassette, [miss], []))
        flow.response = _json(
            418,
            {"wireMiss": True, **miss.model_dump(mode="json", exclude={"body"})},
            {"X-Wire-Miss": "1"},
        )

    def _answer(self, flow: http.HTTPFlow) -> http.Response:
        request = flow.request
        host = request.pretty_host
        path = urlsplit(request.path).path
        if host == OPENAI_HOST:
            return _json(401, _OPENAI_REFUSAL)
        if host == self.oauth_host and path.endswith("/jwks"):
            return _json(200, self.key.jwks())
        token = _token(request)
        claims = token_claims(token) if token else None
        if claims is not None and not claims.is_guest:
            if claims.e2e_cassette is None:
                self._refuse(flow, STACK, "no-cassette", self._stack_misses)
                return flow.response or _json(418, {})
            return self._from_cassette(flow, claims.e2e_cassette)
        return self._from_cassette(flow, STACK)

    def _from_cassette(self, flow: http.HTTPFlow, cassette: str) -> http.Response:
        request = flow.request
        path = urlsplit(request.path).path
        email = cassette_email(cassette)
        if cassette != STACK and request.method == "GET" and _CURRENT_USER.search(path):
            return _json(200, self._current_user(email))
        body = re.sub(
            re.escape(email).encode(),
            ACCOUNT_EMAIL.encode(),
            request.content or b"",
            flags=re.IGNORECASE,
        )
        key = exchange_key(
            request.pretty_host, request.method, path, _query(request), body
        )
        write = changes_user_state(request.method, path)
        played = self._played_for(cassette)
        exchange = played.take(key, write=write)
        misses = (
            self._stack_misses
            if cassette == STACK
            else self._misses.setdefault(cassette, [])
        )
        if exchange is None:
            reason: MissReason = (
                "used-up" if write and played.knows(key) else "unrecorded"
            )
            self._refuse(flow, cassette, reason, misses)
            return flow.response or _json(418, {})
        content = self.store.read_body(exchange.response) if exchange.response else b""
        content = content.replace(ACCOUNT_EMAIL.encode(), email.encode())
        response = http.Response.make(exchange.status, content)
        if exchange.content_type:
            response.headers["content-type"] = exchange.content_type
        for name in exchange.set_cookies:
            value = HERMETIC_GUEST_TOKEN if name == "Authorization" else REDACTED
            response.headers.add("set-cookie", f"{name}={value}; Path=/")
        return response

    @staticmethod
    def _current_user(email: str) -> JSONObject:
        return {
            "id": FAKE_USER_ID,
            "email": email,
            "isGuest": False,
            "properties": {
                "firstName": ACCOUNT_FIRST_NAME,
                "lastName": ACCOUNT_LAST_NAME,
                "organization": ACCOUNT_ORGANIZATION,
            },
        }

    def _note_secrets(self, request: http.Request) -> None:
        token = _token(request)
        if token:
            self._secrets.add(token)
        self._secrets.update(request.headers.get_all("auth-key"))
        self._secrets.update(value for _, value in request.cookies.items(multi=True))

    def _skipped(self, request: http.Request, credential: Credential) -> bool:
        host = request.pretty_host
        path = urlsplit(request.path).path
        if host in {OPENAI_HOST, self.oauth_host} or path.endswith("/login"):
            return True
        return (
            credential == "registered"
            and request.method == "GET"
            and bool(_CURRENT_USER.search(path))
        )

    def _record(self, flow: http.HTTPFlow, response: http.Response) -> None:
        request = flow.request
        token = _token(request)
        credential = _credential(token)
        content = response.content or b""
        self._secrets.update(
            cookie.split(";", 1)[0].partition("=")[2]
            for cookie in response.headers.get_all("set-cookie")
        )
        self._learn(request, credential, content)
        if self._skipped(request, credential):
            return
        cassette = STACK
        if credential == "registered" and self._active is not None:
            cassette = self._active
        path = urlsplit(request.path).path
        seen = self._recorded.setdefault(cassette, [])
        writes = self._writes.get(cassette, 0)
        body, base64 = stored_body(request.content or b"")
        exchange = Exchange(
            seq=len(seen),
            host=request.pretty_host,
            method=request.method,
            path=path,
            query=_query(request),
            body=body,
            body_base64=base64,
            credential=credential,
            epoch=writes,
            status=response.status_code,
            content_type=response.headers.get("content-type", ""),
            set_cookies=[
                cookie.split("=", 1)[0].strip()
                for cookie in response.headers.get_all("set-cookie")
            ],
            ms=round(
                1000
                * ((response.timestamp_end or time.time()) - request.timestamp_start),
                1,
            ),
        )
        seen.append(_Seen(exchange=exchange, response=content))
        if exchange.is_write():
            self._writes[cassette] = writes + 1

    def _learn(
        self, request: http.Request, credential: Credential, content: bytes
    ) -> None:
        path = urlsplit(request.path).path
        if credential == "registered" and _CURRENT_USER.search(path):
            try:
                user = _CurrentUser.model_validate_json(content)
            except ValidationError:
                return
            if not user.isGuest and user.email:
                self._identity = Identity(
                    user_id=user.id,
                    email=user.email,
                    first_name=user.properties.get("firstName", ""),
                    last_name=user.properties.get("lastName", ""),
                    organization=user.properties.get("organization", ""),
                )
            return
        try:
            self._builds[request.pretty_host] = _ServiceRoot.model_validate_json(
                content
            ).buildNumber
        except ValidationError:
            return

    def _write(self, cassette: str) -> None:
        seen = self._recorded.pop(cassette, [])
        if self._identity is None:
            msg = "the recorder saw no /users/current answer, so it cannot redact"
            raise LeakError(msg)
        redactor = Redactor(self._identity, self._secrets)
        store = WireStore(self.store.root, guard=redactor)
        exchanges = []
        for item in seen:
            exchange = item.exchange
            body = redactor.body(exchange.request_bytes())
            text, base64 = stored_body(body)
            exchanges.append(
                exchange.model_copy(
                    update={
                        "path": redactor.path(exchange.path),
                        "query": [(k, redactor.path(v)) for k, v in exchange.query],
                        "body": text,
                        "body_base64": base64,
                        "response": store.put_body(redactor.body(item.response))
                        if item.response
                        else None,
                    }
                )
            )
        hosts = {exchange.host for exchange in exchanges}
        recorded = Cassette(
            header=CassetteHeader(
                cassette=cassette,
                recorded_at=datetime.now(UTC),
                builds={h: b for h, b in self._builds.items() if h in hosts},
            ),
            exchanges=exchanges,
        )
        if cassette == STACK:
            recorded = merge_stack(self.store.read_cassette(STACK), recorded)
        store.write_cassette(recorded)
