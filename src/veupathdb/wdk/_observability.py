"""Observability helpers for VEuPathDB HTTP clients."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from tenacity import RetryCallState

from veupathdb.logging import get_logger
from veupathdb.observer import get_observer

logger = get_logger(__name__)
_ENDPOINT_GROUP_PREFIXES = (
    ("record-types/", "record_types"),
    ("searches/", "searches"),
    ("strategies/", "strategies"),
    ("steps/", "steps"),
    ("answers/", "answers"),
    ("users/", "users"),
    ("reports/", "reports"),
    ("site-search", "site_search"),
)


def _status_family(status_code: int | None) -> str:
    if status_code is None:
        return "none"
    return f"{status_code // 100}xx"


def _site_host(base_url: str) -> str:
    return urlparse(base_url).hostname or "unknown"


def _endpoint_group(path: str) -> str:
    normalized = path.lstrip("/")
    for prefix, group in _ENDPOINT_GROUP_PREFIXES:
        if normalized.startswith(prefix):
            return group
    return "other"


def _error_kind(error: BaseException) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.ConnectError):
        return "connect_error"
    if isinstance(error, httpx.HTTPStatusError):
        return f"http_{_status_family(error.response.status_code)}"
    if isinstance(error, httpx.RequestError):
        return "request_error"
    return type(error).__name__


@dataclass(frozen=True)
class _RequestMetricContext:
    method: str
    path: str
    base_url: str
    has_auth: bool


def _request_metric_attrs(
    *,
    context: _RequestMetricContext,
    outcome: str,
    status_code: int | None = None,
    retried: bool | None = None,
) -> dict[str, str]:
    attrs = {
        "method": context.method,
        "endpoint_group": _endpoint_group(context.path),
        "site_host": _site_host(context.base_url),
        "has_auth": str(context.has_auth).lower(),
        "status_family": _status_family(status_code),
        "outcome": outcome,
    }
    if retried is not None:
        attrs["retried"] = str(retried).lower()
    return attrs


@dataclass(frozen=True)
class WdkRequestTelemetry:
    """Low-cardinality observability context for one logical WDK request."""

    method: str
    path: str
    base_url: str
    has_auth: bool

    def metric_attrs(
        self,
        *,
        outcome: str,
        status_code: int | None = None,
        retried: bool | None = None,
    ) -> dict[str, str]:
        return _request_metric_attrs(
            context=_RequestMetricContext(
                method=self.method,
                path=self.path,
                base_url=self.base_url,
                has_auth=self.has_auth,
            ),
            outcome=outcome,
            status_code=status_code,
            retried=retried,
        )


@dataclass(frozen=True)
class SiteSearchRequestTelemetry:
    """Low-cardinality observability context for one logical site-search request."""

    method: str
    path: str
    base_url: str

    def metric_attrs(
        self,
        *,
        outcome: str,
        status_code: int | None = None,
        retried: bool | None = None,
    ) -> dict[str, str]:
        return _request_metric_attrs(
            context=_RequestMetricContext(
                method=self.method,
                path=self.path,
                base_url=self.base_url,
                has_auth=False,
            ),
            outcome=outcome,
            status_code=status_code,
            retried=retried,
        )


def _retry_failure(retry_state: RetryCallState) -> tuple[float, BaseException] | None:
    """The pending sleep and the failure, when the state carries both."""
    next_action = retry_state.next_action
    if next_action is None:
        return None
    outcome = retry_state.outcome
    if outcome is None or not outcome.failed:
        return None
    error = outcome.exception()
    if error is None:
        return None
    sleep = next_action.sleep
    return (float(sleep) if sleep is not None else 0.0, error)


def wdk_retry_logger(
    telemetry: WdkRequestTelemetry,
) -> Callable[[RetryCallState], None]:
    """Build a tenacity before_sleep hook bound to one request's telemetry."""

    def log_retry(retry_state: RetryCallState) -> None:
        failure = _retry_failure(retry_state)
        if failure is None:
            return
        wait_seconds, error = failure
        attrs = telemetry.metric_attrs(
            outcome="retry",
            status_code=(
                error.response.status_code
                if isinstance(error, httpx.HTTPStatusError)
                else None
            ),
            retried=True,
        )
        get_observer().on_wdk_retry(attrs | {"error_kind": _error_kind(error)})
        logger.warning(
            "Retrying VEuPathDB request",
            method=telemetry.method,
            path=telemetry.path,
            endpoint_group=attrs["endpoint_group"],
            site_host=attrs["site_host"],
            attempt=retry_state.attempt_number,
            wait_seconds=wait_seconds,
            error_kind=_error_kind(error),
            error=str(error),
        )

    return log_retry


def site_search_retry_logger(
    telemetry: SiteSearchRequestTelemetry,
) -> Callable[[RetryCallState], None]:
    """Build a tenacity before_sleep hook bound to one request's telemetry."""

    def log_retry(retry_state: RetryCallState) -> None:
        failure = _retry_failure(retry_state)
        if failure is None:
            return
        wait_seconds, error = failure
        attrs = telemetry.metric_attrs(outcome="retry", retried=True)
        get_observer().on_site_search_retry(attrs | {"error_kind": _error_kind(error)})
        logger.warning(
            "Retrying site-search request",
            method=telemetry.method,
            path=telemetry.path,
            endpoint_group=attrs["endpoint_group"],
            site_host=attrs["site_host"],
            attempt=retry_state.attempt_number,
            wait_seconds=wait_seconds,
            error_kind=_error_kind(error),
            error=str(error),
        )

    return log_retry
