from collections.abc import AsyncIterator, Iterator

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.errors import JBrowseError

BASE = "https://qa.plasmodb.org/plasmo.qa"


@pytest.fixture(autouse=True)
def registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


def client(handler: httpx.MockTransport) -> JBrowseClient:
    return JBrowseClient(base_url=BASE, transport=handler)


class WatchedBody(httpx.AsyncByteStream):
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.reads = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.reads += 1
        if self.reads > 1:
            raise AssertionError
        yield self.body

    async def aclose(self) -> None:
        self.closed = True


def answering(status: int, body: WatchedBody) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, stream=body))


async def test_a_track_list_is_read_from_the_organism_path() -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"tracks": [{"label": "t"}]})

    listed = await client(httpx.MockTransport(answer)).track_list(
        "organismSpecific", "pfal3D7"
    )
    assert [t.label for t in listed.tracks] == ["t"]
    assert seen[0].url.path == "/plasmo.qa/service/jbrowse/organismSpecific/pfal3D7"
    assert seen[0].headers["Cookie"] == "Authorization=token-hermetic"


async def test_a_ranged_read_sends_the_range_and_needs_partial_content() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=10-19"
        assert (
            request.url.params["data"] == "pfal3D7/genomeAndProteome/fasta/genome.fasta"
        )
        return httpx.Response(206, content=b"ACGTACGTAC")

    body = await client(httpx.MockTransport(answer)).store_bytes(
        "pfal3D7/genomeAndProteome/fasta/genome.fasta", (10, 19)
    )
    assert body == b"ACGTACGTAC"


async def test_a_store_that_ignores_the_range_is_refused() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"A" * 1000)

    with pytest.raises(JBrowseError) as raised:
        await client(httpx.MockTransport(answer)).store_bytes("x/genome.fasta", (0, 9))
    assert (raised.value.upstream_status, raised.value.status) == (200, 502)


async def test_an_error_status_is_raised() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    with pytest.raises(JBrowseError) as raised:
        await client(httpx.MockTransport(answer)).track_list("rnaseq", "pfal3D7")
    assert (raised.value.upstream_status, raised.value.status) == (404, 502)


async def test_a_registered_token_refused_is_raised_without_a_retry() -> None:
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(401, text="Unauthorized")

    with pytest.raises(JBrowseError) as raised:
        await client(httpx.MockTransport(answer)).track_list("rnaseq", "pfal3D7")
    assert (raised.value.upstream_status, raised.value.status) == (401, 502)
    assert len(sent) == 1


def test_a_jbrowse_error_is_a_service_refusal() -> None:
    error = JBrowseError("GET", f"{BASE}/service/jbrowse/store", 404)
    assert isinstance(error, VEuPathDBError)
    assert error.code == VEuPathDBErrorCode.EXTERNAL_SERVICE_ERROR
    assert error.title == "Genome browser service error"
    assert error.detail == f"GET {BASE}/service/jbrowse/store answered 404"
    assert (error.method, error.url, error.upstream_status, error.status) == (
        "GET",
        f"{BASE}/service/jbrowse/store",
        404,
        502,
    )


async def test_a_redirect_to_a_login_page_is_raised() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            307,
            headers={"Location": f"{BASE}/app/user/login"},
            text="<html>Temporary Redirect</html>",
        )

    with pytest.raises(JBrowseError) as raised:
        await client(httpx.MockTransport(answer)).track_list(
            "organismSpecific", "pfal3D7"
        )
    assert (raised.value.upstream_status, raised.value.status) == (307, 502)


async def test_a_store_that_ignores_the_range_is_refused_unread() -> None:
    body = WatchedBody(b"A" * 1000)
    with pytest.raises(JBrowseError) as raised:
        await client(answering(200, body)).store_bytes("x/genome.fasta", (0, 9))
    assert raised.value.upstream_status == 200
    assert (body.reads, body.closed) == (0, True)


async def test_an_error_status_is_refused_unread() -> None:
    body = WatchedBody(b"<html>Not Found</html>")
    with pytest.raises(JBrowseError) as raised:
        await client(answering(404, body)).store_bytes("x/genome.fasta")
    assert raised.value.upstream_status == 404
    assert (body.reads, body.closed) == (0, True)


async def test_a_partial_answer_is_read_once_and_closed() -> None:
    body = WatchedBody(b"ACGTACGTAC")
    read = await client(answering(206, body)).store_bytes("x/genome.fasta", (0, 9))
    assert read == b"ACGTACGTAC"
    assert (body.reads, body.closed) == (1, True)
