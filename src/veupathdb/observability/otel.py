"""An OpenTelemetry sink for the client's observer. Needs the ``otel`` extra.

The instruments are created on the global metrics API, so they record nothing
until the host configures a ``MeterProvider``.
"""

from opentelemetry import metrics

from veupathdb.observer import MetricAttrs

_wdk_meter = metrics.get_meter("veupathdb.wdk")
_site_search_meter = metrics.get_meter("veupathdb.site_search")

wdk_requests = _wdk_meter.create_counter(
    "veupathdb.wdk.requests",
    description="Logical WDK requests by endpoint family and outcome",
    unit="{request}",
)

wdk_request_retries = _wdk_meter.create_counter(
    "veupathdb.wdk.request_retries",
    description="Retry attempts for transient WDK request failures",
    unit="{retry}",
)

wdk_request_duration_s = _wdk_meter.create_histogram(
    "veupathdb.wdk.request_duration",
    description="WDK HTTP request duration including retries",
    unit="s",
)

site_search_requests = _site_search_meter.create_counter(
    "veupathdb.site_search.requests",
    description="Logical site-search requests by outcome",
    unit="{request}",
)

site_search_request_retries = _site_search_meter.create_counter(
    "veupathdb.site_search.request_retries",
    description="Retry attempts for transient site-search request failures",
    unit="{retry}",
)

site_search_request_duration_s = _site_search_meter.create_histogram(
    "veupathdb.site_search.request_duration",
    description="Site-search HTTP request duration including retries",
    unit="s",
)


class OpenTelemetryObserver:
    """Feeds the WDK and site-search instruments the client reports to."""

    def on_wdk_request(self, seconds: float, attrs: MetricAttrs, /) -> None:
        wdk_requests.add(1, attrs)
        wdk_request_duration_s.record(seconds, attrs)

    def on_wdk_retry(self, attrs: MetricAttrs, /) -> None:
        wdk_request_retries.add(1, attrs)

    def on_site_search_request(self, seconds: float, attrs: MetricAttrs, /) -> None:
        site_search_requests.add(1, attrs)
        site_search_request_duration_s.record(seconds, attrs)

    def on_site_search_retry(self, attrs: MetricAttrs, /) -> None:
        site_search_request_retries.add(1, attrs)


__all__ = [
    "OpenTelemetryObserver",
]
