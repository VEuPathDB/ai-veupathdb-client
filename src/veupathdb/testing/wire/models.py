from __future__ import annotations

import base64
import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from veupathdb.testing.wire.key import exchange_key
from veupathdb.wdk._http import changes_user_state

Credential = Literal["registered", "guest", "none"]

STACK = "stack"

_CASSETTE = re.compile(r"[A-Za-z0-9@._-]+(?:/[A-Za-z0-9@._-]+)*")


def _inside_the_tree(cassette: str) -> str:
    segments = cassette.split("/")
    if not _CASSETTE.fullmatch(cassette) or any(s in {".", ".."} for s in segments):
        msg = f"{cassette!r} is not a cassette id"
        raise ValueError(msg)
    return cassette


CassetteId = Annotated[str, AfterValidator(_inside_the_tree)]
BodyHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class Exchange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int
    host: str
    method: str
    path: str
    query: list[tuple[str, str]] = Field(default_factory=list)
    body: str | None = None
    body_base64: bool = False
    credential: Credential
    epoch: int
    status: int
    content_type: str = ""
    set_cookies: list[str] = Field(default_factory=list)
    response: BodyHash | None = None
    ms: float = 0.0

    def request_bytes(self) -> bytes:
        if self.body is None:
            return b""
        if self.body_base64:
            return base64.b64decode(self.body)
        return self.body.encode()

    def key(self) -> str:
        return exchange_key(
            self.host, self.method, self.path, self.query, self.request_bytes()
        )

    def is_write(self) -> bool:
        return changes_user_state(self.method, self.path)


def stored_body(body: bytes) -> tuple[str | None, bool]:
    if not body:
        return None, False
    try:
        return body.decode("utf-8"), False
    except UnicodeDecodeError:
        return base64.b64encode(body).decode(), True


class CassetteHeader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cassette: CassetteId
    recorded_at: datetime
    builds: dict[str, int] = Field(default_factory=dict)


class Cassette(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    header: CassetteHeader
    exchanges: list[Exchange] = Field(default_factory=list)


class HostRecordings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    builds: dict[int, int] = Field(default_factory=dict)
    oldest: datetime
    newest: datetime


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cassettes: int = 0
    hosts: dict[str, HostRecordings] = Field(default_factory=dict)
    libraries: dict[str, str] = Field(default_factory=dict)
