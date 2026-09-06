"""Tests for WDK HTTP observability helpers."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode, WDKError
from veupathdb.observer import MetricAttrs, get_observer, set_observer
from veupathdb.wdk._http import HTTPClient
from veupathdb.wdk._observability import (
    SiteSearchRequestTelemetry,
    WdkRequestTelemetry,
)
from veupathdb.wdk.site_search_client import (
    SiteSearchClient,
    SiteSearchResponse,
)


class _RecordingObserver:
    """Keeps every call the client makes, so a test can read the labels back."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, float, MetricAttrs]] = []
        self.retries: list[tuple[str, MetricAttrs]] = []

    def on_wdk_request(self, seconds: float, attrs: MetricAttrs, /) -> None:
        self.requests.append(("wdk", seconds, attrs))

    def on_wdk_retry(self, attrs: MetricAttrs, /) -> None:
        self.retries.append(("wdk", attrs))

    def on_site_search_request(self, seconds: float, attrs: MetricAttrs, /) -> None:
        self.requests.append(("site_search", seconds, attrs))

    def on_site_search_retry(self, attrs: MetricAttrs, /) -> None:
        self.retries.append(("site_search", attrs))


@pytest.fixture
def observer() -> Iterator[_RecordingObserver]:
    recording = _RecordingObserver()
    previous = get_observer()
    set_observer(recording)
    try:
        yield recording
    finally:
        set_observer(previous)


def test_wdk_request_telemetry_builds_low_cardinality_attrs() -> None:
    telemetry = WdkRequestTelemetry(
        method="GET",
        path="/record-types/gene/searches/GenesByText",
        base_url="https://plasmodb.org/plasmo/service",
        has_auth=True,
    )

    attrs = telemetry.metric_attrs(outcome="ok", status_code=200, retried=False)

    assert attrs == {
        "method": "GET",
        "endpoint_group": "record_types",
        "site_host": "plasmodb.org",
        "has_auth": "true",
        "status_family": "2xx",
        "outcome": "ok",
        "retried": "false",
    }


@pytest.mark.asyncio
async def test_wdk_retry_log_names_the_request_and_never_the_token(
    observer: _RecordingObserver,
) -> None:
    """The retry warning carries the request's method/path, never the token."""
    client = HTTPClient(
        "https://plasmodb.org/plasmo/service",
        auth_token="secret-token",
    )
    attempt = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with (
        patch.object(client, "_request_attempt", attempt),
        patch("veupathdb.wdk._observability.logger") as mock_logger,
        pytest.raises(WDKError),
    ):
        await client._request("GET", "/record-types/gene/searches/GenesByText")

    assert attempt.await_count == 3
    assert mock_logger.warning.call_count == 2
    for warning in mock_logger.warning.call_args_list:
        assert warning.kwargs["method"] == "GET"
        assert warning.kwargs["path"] == "/record-types/gene/searches/GenesByText"
        assert warning.kwargs["site_host"] == "plasmodb.org"
        assert "secret-token" not in repr(warning)
    retry_attrs = observer.retries[-1][1]
    assert retry_attrs["endpoint_group"] == "record_types"
    assert retry_attrs["site_host"] == "plasmodb.org"
    assert retry_attrs["has_auth"] == "true"
    assert retry_attrs["error_kind"] == "connect_error"


def test_site_search_request_telemetry_builds_expected_attrs() -> None:
    telemetry = SiteSearchRequestTelemetry(
        method="POST",
        path="/site-search",
        base_url="https://plasmodb.org",
    )

    attrs = telemetry.metric_attrs(outcome="ok", status_code=200, retried=False)

    assert attrs == {
        "method": "POST",
        "endpoint_group": "site_search",
        "site_host": "plasmodb.org",
        "has_auth": "false",
        "status_family": "2xx",
        "outcome": "ok",
        "retried": "false",
    }


@pytest.mark.asyncio
async def test_site_search_retry_log_names_the_request(
    observer: _RecordingObserver,
) -> None:
    """The site-search retry warning carries the request's path and host."""
    client = SiteSearchClient("https://plasmodb.org", "PlasmoDB")
    http_client = AsyncMock()
    http_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with (
        patch.object(client, "_get_client", AsyncMock(return_value=http_client)),
        patch("veupathdb.wdk._observability.logger") as mock_logger,
        pytest.raises(VEuPathDBError),
    ):
        await client.search("transporters")

    assert mock_logger.warning.call_count == 2
    for warning in mock_logger.warning.call_args_list:
        assert warning.kwargs["method"] == "POST"
        assert warning.kwargs["path"] == "/site-search"
        assert warning.kwargs["site_host"] == "plasmodb.org"
    retry_attrs = observer.retries[-1][1]
    assert retry_attrs["endpoint_group"] == "site_search"
    assert retry_attrs["error_kind"] == "timeout"


@pytest.mark.asyncio
async def test_site_search_client_records_success_metrics(
    observer: _RecordingObserver,
) -> None:
    client = SiteSearchClient("https://plasmodb.org", "PlasmoDB")
    response = SiteSearchResponse()

    with patch.object(client, "_search_attempt", AsyncMock(return_value=response)):
        result = await client.search("transporter")

    assert result is response
    expected_attrs = {
        "method": "POST",
        "endpoint_group": "site_search",
        "site_host": "plasmodb.org",
        "has_auth": "false",
        "status_family": "2xx",
        "outcome": "ok",
    }
    assert len(observer.requests) == 1
    family, duration, attrs = observer.requests[0]
    assert family == "site_search"
    assert duration >= 0.0
    assert attrs == expected_attrs


@pytest.mark.asyncio
async def test_site_search_client_records_error_metrics(
    observer: _RecordingObserver,
) -> None:
    client = SiteSearchClient("https://plasmodb.org", "PlasmoDB")
    error = VEuPathDBError(VEuPathDBErrorCode.WDK_ERROR, "site-search failed")

    with (
        patch.object(client, "_search_attempt", AsyncMock(side_effect=error)),
        pytest.raises(VEuPathDBError, match="site-search failed"),
    ):
        await client.search("transporter")

    expected_attrs = {
        "method": "POST",
        "endpoint_group": "site_search",
        "site_host": "plasmodb.org",
        "has_auth": "false",
        "status_family": "none",
        "outcome": "error",
    }
    assert len(observer.requests) == 1
    family, duration, attrs = observer.requests[0]
    assert family == "site_search"
    assert duration >= 0.0
    assert attrs == expected_attrs
