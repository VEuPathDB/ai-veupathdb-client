from __future__ import annotations

import asyncio

import httpx
import pytest

from veupathdb.errors import WDKError
from veupathdb.wdk._http import runs_a_search
from veupathdb.wdk.client import VEuPathDBClient

SEARCH_PATHS = [
    ("POST", "/record-types/transcript/searches/GenesByNgsSnps/reports/standard"),
    ("POST", "/users/1/steps/9/reports/standard"),
    ("POST", "/users/1/steps/9/reports/fullRecord"),
    ("POST", "/users/1/steps/9/columns/gene_id/reports/byValue"),
    ("POST", "/users/1/steps/9/analyses/4/result"),
    ("GET", "/users/1/steps/9"),
    ("GET", "/users/1/strategies/5"),
]
METADATA_PATHS = [
    ("GET", "/record-types/transcript/searches/GenesByNgsSnps"),
    ("GET", "/users/1/strategies"),
    ("GET", "/users/1/steps/9/analyses/4/result/status"),
    ("POST", "/users/1/steps"),
    ("PATCH", "/users/1/steps/9"),
    ("GET", "/users/current"),
]


@pytest.mark.parametrize(("method", "path"), SEARCH_PATHS)
def test_a_request_that_makes_wdk_run_a_search_is_one(method: str, path: str) -> None:
    assert runs_a_search(method, path) is True


@pytest.mark.parametrize(("method", "path"), METADATA_PATHS)
def test_a_request_that_reads_or_writes_no_answer_is_not_one(
    method: str, path: str
) -> None:
    assert runs_a_search(method, path) is False


class _Answering(httpx.AsyncBaseTransport):
    def __init__(self, status: int = 200, *, connect_failures: int = 0) -> None:
        self.status = status
        self.connect_failures = connect_failures
        self.sent: list[str] = []
        self.in_flight = 0
        self.most_in_flight = 0
        self.release = asyncio.Event()
        self.release.set()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/app"):
            return httpx.Response(200, text="ok")
        self.sent.append(request.url.path)
        if self.connect_failures > 0:
            self.connect_failures -= 1
            msg = "refused"
            raise httpx.ConnectError(msg, request=request)
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        await self.release.wait()
        self.in_flight -= 1
        if self.status >= 500:
            return httpx.Response(self.status, text="Server Error")
        return httpx.Response(
            200, json={"id": 1}, headers={"content-type": "application/json"}
        )


class _TimingOut(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.sent = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/app"):
            return httpx.Response(200, text="ok")
        self.sent += 1
        msg = "slow"
        raise httpx.ReadTimeout(msg, request=request)


async def _client(
    transport: httpx.AsyncBaseTransport, *, concurrent_searches: int = 4
) -> VEuPathDBClient:
    client = VEuPathDBClient(
        base_url="https://example.invalid/service",
        concurrent_searches=concurrent_searches,
    )
    async with client._client_lock:
        client._client = httpx.AsyncClient(
            base_url=client.base_url, transport=transport, follow_redirects=True
        )
    return client


@pytest.mark.usefixtures("wdk_request_token")
class TestASearchIsSentOnce:
    async def test_a_server_error_on_a_report_is_not_sent_again(self) -> None:
        transport = _Answering(status=502)
        client = await _client(transport)

        with pytest.raises(WDKError) as raised:
            await client.post("/users/1/steps/9/reports/standard", json={})

        assert raised.value.status == 502
        assert transport.sent == ["/service/users/1/steps/9/reports/standard"]

    async def test_a_timed_out_search_is_not_sent_again(self) -> None:
        transport = _TimingOut()
        client = await _client(transport)

        with pytest.raises(WDKError):
            await client.post(
                "/record-types/transcript/searches/GenesByNgsSnps/reports/standard",
                json={},
            )

        assert transport.sent == 1

    async def test_a_search_that_never_connected_is_sent_again(self) -> None:
        transport = _Answering(connect_failures=1)
        client = await _client(transport)

        assert await client.get("/users/1/steps/9") == {"id": 1}
        assert transport.sent == ["/service/users/1/steps/9"] * 2

    async def test_a_metadata_read_still_recovers_from_a_server_error(self) -> None:
        transport = _Answering(status=502)
        client = await _client(transport)

        with pytest.raises(WDKError):
            await client.get("/record-types/transcript/searches/GenesByNgsSnps")

        assert len(transport.sent) == 3


@pytest.mark.usefixtures("wdk_request_token")
class TestSearchesWaitForASlot:
    async def test_no_more_searches_run_at_once_than_the_site_allows(self) -> None:
        transport = _Answering()
        transport.release.clear()
        client = await _client(transport, concurrent_searches=2)

        reports = [
            asyncio.create_task(
                client.post(f"/users/1/steps/{step}/reports/standard", json={})
            )
            for step in range(6)
        ]
        await asyncio.sleep(0.05)
        waiting_at_the_cap = transport.in_flight
        transport.release.set()
        await asyncio.gather(*reports)

        assert waiting_at_the_cap == 2
        assert transport.most_in_flight == 2
        assert len(transport.sent) == 6

    async def test_a_metadata_read_does_not_wait_behind_searches(self) -> None:
        transport = _Answering()
        transport.release.clear()
        client = await _client(transport, concurrent_searches=1)
        held = asyncio.create_task(
            client.post("/users/1/steps/1/reports/standard", json={})
        )
        await asyncio.sleep(0.05)

        read = asyncio.create_task(client.get("/users/1/strategies"))
        await asyncio.sleep(0.05)

        assert transport.in_flight == 2
        transport.release.set()
        await asyncio.gather(held, read)
