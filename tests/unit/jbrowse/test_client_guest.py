from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator

import httpx
import jwt
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import WDKLoginRequiredError
from veupathdb.guest_token import GuestTokens, guest_tokens, use_guest_tokens
from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.observer import MetricAttrs, NoObserver, get_observer, set_observer

PLASMO_WEB = "https://qa.plasmodb.org/plasmo.qa"
PLASMO_SERVICE = "https://qa.plasmodb.org/plasmo.qa/service"
EXPIRES = int(time.time()) + 3600


def guest(serial: int) -> str:
    return jwt.encode(
        {"is_guest": True, "exp": EXPIRES, "sub": f"guest-{serial}"},
        "a-hermetic-signing-key-of-at-least-32-bytes",
        algorithm="HS256",
    )


@pytest.fixture
def mints() -> Iterator[list[str]]:
    minted_at: list[str] = []

    def mint(request: httpx.Request) -> httpx.Response:
        minted_at.append(str(request.url))
        token = guest(len(minted_at))
        return httpx.Response(
            200, headers={"set-cookie": f"Authorization={token};Path=/"}
        )

    held = guest_tokens()
    reset = veupathdb_auth_token_ctx.set(None)
    use_guest_tokens(GuestTokens(transport=httpx.MockTransport(mint)))
    try:
        yield minted_at
    finally:
        use_guest_tokens(held)
        veupathdb_auth_token_ctx.reset(reset)


def jbrowse(statuses: list[int], sent: list[httpx.Request]) -> JBrowseClient:
    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(statuses[len(sent) - 1], json={"tracks": []})

    return JBrowseClient(base_url=PLASMO_WEB, transport=httpx.MockTransport(answer))


async def test_a_read_without_a_token_travels_as_the_guest_of_its_site(
    mints: list[str],
) -> None:
    sent: list[httpx.Request] = []
    await jbrowse([200], sent).track_list("organismSpecific", "pfal3D7")
    assert mints == [PLASMO_SERVICE]
    assert sent[0].headers["Cookie"] == f"Authorization={guest(1)}"


async def test_a_refused_guest_is_renewed_and_the_read_sent_again(
    mints: list[str],
) -> None:
    sent: list[httpx.Request] = []
    await jbrowse([401, 200], sent).track_list("organismSpecific", "pfal3D7")
    assert mints == [PLASMO_SERVICE, PLASMO_SERVICE]
    assert [r.headers["Cookie"] for r in sent] == [
        f"Authorization={guest(1)}",
        f"Authorization={guest(2)}",
    ]


async def test_a_renewed_guest_refused_again_needs_a_login(
    mints: list[str],
) -> None:
    sent: list[httpx.Request] = []
    with pytest.raises(WDKLoginRequiredError):
        await jbrowse([401, 401], sent).store_bytes("x/genome.fasta", (0, 9))
    assert len(mints) == 2
    assert len(sent) == 2


class RefusedBody(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.reads = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.reads += 1
        yield b"Unauthorized"

    async def aclose(self) -> None:
        self.closed = True


async def test_every_refused_guest_answer_is_closed_unread(
    mints: list[str],
) -> None:
    bodies = [RefusedBody(), RefusedBody()]

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, stream=bodies[len(mints) - 1])

    reader = JBrowseClient(base_url=PLASMO_WEB, transport=httpx.MockTransport(answer))
    with pytest.raises(WDKLoginRequiredError):
        await reader.store_bytes("x/genome.fasta", (0, 9))
    assert [(b.reads, b.closed) for b in bodies] == [(0, True), (0, True)]


class RecordingObserver(NoObserver):
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def on_jbrowse_request(self, seconds: float, attrs: MetricAttrs, /) -> None:
        self.statuses.append(attrs["status"])


@pytest.fixture
def observer() -> Iterator[RecordingObserver]:
    recording = RecordingObserver()
    previous = get_observer()
    set_observer(recording)
    try:
        yield recording
    finally:
        set_observer(previous)


async def test_a_renewed_guest_read_reports_each_request(
    mints: list[str], observer: RecordingObserver
) -> None:
    await jbrowse([401, 200], []).track_list("organismSpecific", "pfal3D7")
    assert observer.statuses == ["401", "200"]


async def test_a_guest_refused_twice_reports_both_requests(
    mints: list[str], observer: RecordingObserver
) -> None:
    with pytest.raises(WDKLoginRequiredError):
        await jbrowse([401, 401], []).store_bytes("x/genome.fasta", (0, 9))
    assert observer.statuses == ["401", "401"]
