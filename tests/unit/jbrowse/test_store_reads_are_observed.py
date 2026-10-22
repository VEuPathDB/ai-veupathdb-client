from collections.abc import Iterator

import httpx
import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import HistogramDataPoint, InMemoryMetricReader

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.errors import JBrowseError
from veupathdb.observability import otel
from veupathdb.observability.otel import OpenTelemetryObserver
from veupathdb.observer import (
    MetricAttrs,
    NoObserver,
    Observer,
    get_observer,
    set_observer,
)

BASE = "https://qa.plasmodb.org/plasmo.qa"
PATH = "org1/genomeBrowser/bigwig/coverage.bw"


class RecordingObserver(NoObserver):
    def __init__(self) -> None:
        self.reads: list[tuple[float, dict[str, str]]] = []

    def on_jbrowse_request(self, seconds: float, attrs: MetricAttrs, /) -> None:
        self.reads.append((seconds, dict(attrs)))


@pytest.fixture(autouse=True)
def registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


@pytest.fixture
def observer() -> Iterator[RecordingObserver]:
    recording = RecordingObserver()
    previous = get_observer()
    set_observer(recording)
    try:
        yield recording
    finally:
        set_observer(previous)


def answering(status: int, body: bytes) -> JBrowseClient:
    return JBrowseClient(
        base_url=BASE,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, content=body)
        ),
    )


async def test_a_store_range_read_is_observed(observer: RecordingObserver) -> None:
    await answering(206, bytes(100)).store_bytes(PATH, (0, 99))
    assert [attrs for _, attrs in observer.reads] == [
        {"site_host": "qa.plasmodb.org", "kind": "store", "status": "206"}
    ]
    assert observer.reads[0][0] >= 0


async def test_a_track_list_read_is_observed(observer: RecordingObserver) -> None:
    await answering(200, b'{"tracks": []}').track_list("rnaseq", "org1")
    assert [attrs for _, attrs in observer.reads] == [
        {"site_host": "qa.plasmodb.org", "kind": "track_list", "status": "200"}
    ]


async def test_a_refused_read_is_observed_once_then_raised(
    observer: RecordingObserver,
) -> None:
    with pytest.raises(JBrowseError) as raised:
        await answering(500, b"").store_bytes(PATH, (0, 99))
    assert raised.value.upstream_status == 500
    assert [attrs for _, attrs in observer.reads] == [
        {"site_host": "qa.plasmodb.org", "kind": "store", "status": "500"}
    ]


async def test_a_store_that_ignores_the_range_is_observed_with_its_status(
    observer: RecordingObserver,
) -> None:
    with pytest.raises(JBrowseError):
        await answering(200, bytes(1000)).store_bytes(PATH, (0, 99))
    assert [attrs["status"] for _, attrs in observer.reads] == ["200"]


def test_both_observers_take_a_jbrowse_read(monkeypatch: pytest.MonkeyPatch) -> None:
    sink = InMemoryMetricReader()
    histogram = (
        MeterProvider(metric_readers=[sink])
        .get_meter("veupathdb.jbrowse")
        .create_histogram("veupathdb.jbrowse.request_duration")
    )
    attrs = {"site_host": "qa.plasmodb.org", "kind": "store", "status": "206"}
    monkeypatch.setattr(otel, "jbrowse_request_duration_s", histogram)
    observers: list[Observer] = [NoObserver(), OpenTelemetryObserver()]
    for each in observers:
        each.on_jbrowse_request(0.25, attrs)
    data = sink.get_metrics_data()
    assert data is not None
    points = [
        point
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        for point in metric.data.data_points
    ]
    assert len(points) == 1
    point = points[0]
    assert isinstance(point, HistogramDataPoint)
    assert (point.count, point.sum, dict(point.attributes or {})) == (1, 0.25, attrs)


def failing(error: type[httpx.TransportError]) -> JBrowseClient:
    def answer(request: httpx.Request) -> httpx.Response:
        msg = "no answer"
        raise error(msg, request=request)

    return JBrowseClient(base_url=BASE, transport=httpx.MockTransport(answer))


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
async def test_a_read_that_gets_no_answer_is_observed_then_raised(
    observer: RecordingObserver, error: type[httpx.TransportError]
) -> None:
    with pytest.raises(error):
        await failing(error).store_bytes(PATH, (0, 99))
    assert [attrs for _, attrs in observer.reads] == [
        {"site_host": "qa.plasmodb.org", "kind": "store", "status": "none"}
    ]
