"""The client reports through an observer; the OTEL adapter feeds the instruments."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from veupathdb.errors import WDKError
from veupathdb.observability import otel
from veupathdb.observability.otel import OpenTelemetryObserver
from veupathdb.observer import NoObserver, get_observer, set_observer
from veupathdb.wdk._http import HTTPClient
from veupathdb.wdk.site_search_client import SiteSearchClient, SiteSearchResponse

_BASE_URL = "https://plasmodb.org/plasmo/service"
_SEARCH_PATH = "/record-types/gene/searches/GenesByText"


@pytest.fixture
def reader(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemoryMetricReader]:
    sink = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[sink])
    wdk = provider.get_meter("veupathdb.wdk")
    site_search = provider.get_meter("veupathdb.site_search")
    for name, instrument in (
        ("wdk_requests", wdk.create_counter("veupathdb.wdk.requests")),
        ("wdk_request_retries", wdk.create_counter("veupathdb.wdk.request_retries")),
        (
            "wdk_request_duration_s",
            wdk.create_histogram("veupathdb.wdk.request_duration"),
        ),
        (
            "site_search_requests",
            site_search.create_counter("veupathdb.site_search.requests"),
        ),
        (
            "site_search_request_retries",
            site_search.create_counter("veupathdb.site_search.request_retries"),
        ),
        (
            "site_search_request_duration_s",
            site_search.create_histogram("veupathdb.site_search.request_duration"),
        ),
    ):
        monkeypatch.setattr(otel, name, instrument)
    previous = get_observer()
    set_observer(OpenTelemetryObserver())
    try:
        yield sink
    finally:
        set_observer(previous)


def _points(sink: InMemoryMetricReader, name: str) -> list[tuple[Any, dict[str, Any]]]:
    data = sink.get_metrics_data()
    assert data is not None
    return [
        (
            point.value if hasattr(point, "value") else point.count,
            dict(point.attributes),
        )
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == name
        for point in metric.data.data_points
    ]


async def test_a_wdk_call_feeds_the_request_counter_and_the_duration(
    reader: InMemoryMetricReader,
) -> None:
    client = HTTPClient(_BASE_URL, auth_token="a-token")

    with patch.object(client, "_request_attempt", AsyncMock(return_value={"ok": True})):
        await client._request("GET", _SEARCH_PATH)

    expected = {
        "method": "GET",
        "endpoint_group": "record_types",
        "site_host": "plasmodb.org",
        "has_auth": "true",
        "status_family": "2xx",
        "outcome": "ok",
    }
    assert _points(reader, "veupathdb.wdk.requests") == [(1, expected)]
    assert _points(reader, "veupathdb.wdk.request_duration") == [(1, expected)]


async def test_a_refused_wdk_call_records_the_error_outcome(
    reader: InMemoryMetricReader,
) -> None:
    client = HTTPClient(_BASE_URL, auth_token="a-token")
    refusal = WDKError("upstream refused", status=502)

    with (
        patch.object(client, "_request_attempt", AsyncMock(side_effect=refusal)),
        pytest.raises(WDKError),
    ):
        await client._request("GET", _SEARCH_PATH)

    values = _points(reader, "veupathdb.wdk.requests")
    assert len(values) == 1
    count, attrs = values[0]
    assert count == 1
    assert attrs["outcome"] == "error"
    assert attrs["status_family"] == "5xx"


async def test_a_retried_wdk_call_records_the_retry_and_its_error_kind(
    reader: InMemoryMetricReader,
) -> None:
    client = HTTPClient(_BASE_URL, auth_token="a-token")
    attempt = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with (
        patch.object(client, "_request_attempt", attempt),
        pytest.raises(WDKError),
    ):
        await client._request("GET", _SEARCH_PATH)

    retries = _points(reader, "veupathdb.wdk.request_retries")
    assert len(retries) == 1
    count, attrs = retries[0]
    assert count == 2
    assert attrs["error_kind"] == "connect_error"
    assert attrs["outcome"] == "retry"
    assert attrs["retried"] == "true"


async def test_a_site_search_call_feeds_the_site_search_instruments(
    reader: InMemoryMetricReader,
) -> None:
    client = SiteSearchClient("https://plasmodb.org", "PlasmoDB")
    response = SiteSearchResponse()

    with patch.object(client, "_search_attempt", AsyncMock(return_value=response)):
        await client.search("transporter")

    expected = {
        "method": "POST",
        "endpoint_group": "site_search",
        "site_host": "plasmodb.org",
        "has_auth": "false",
        "status_family": "2xx",
        "outcome": "ok",
    }
    assert _points(reader, "veupathdb.site_search.requests") == [(1, expected)]
    assert _points(reader, "veupathdb.site_search.request_duration") == [(1, expected)]


async def test_the_default_observer_records_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counter = MagicMock()
    monkeypatch.setattr(otel, "wdk_requests", counter)
    previous = get_observer()
    set_observer(NoObserver())
    client = HTTPClient(_BASE_URL, auth_token="a-token")

    try:
        with patch.object(
            client, "_request_attempt", AsyncMock(return_value={"ok": True})
        ):
            await client._request("GET", _SEARCH_PATH)
    finally:
        set_observer(previous)

    assert counter.add.call_count == 0
