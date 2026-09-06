"""Where the client reports what a request cost. The host installs the sink."""

from collections.abc import Mapping
from typing import Protocol

type MetricAttrs = Mapping[str, str]


class Observer(Protocol):
    """The instruments one client call feeds."""

    def on_wdk_request(self, seconds: float, attrs: MetricAttrs, /) -> None: ...

    def on_wdk_retry(self, attrs: MetricAttrs, /) -> None: ...

    def on_site_search_request(self, seconds: float, attrs: MetricAttrs, /) -> None: ...

    def on_site_search_retry(self, attrs: MetricAttrs, /) -> None: ...


class NoObserver:
    """Drops every number. A library records nothing the host did not ask for."""

    def on_wdk_request(self, _seconds: float, _attrs: MetricAttrs, /) -> None:
        return None

    def on_wdk_retry(self, _attrs: MetricAttrs, /) -> None:
        return None

    def on_site_search_request(self, _seconds: float, _attrs: MetricAttrs, /) -> None:
        return None

    def on_site_search_retry(self, _attrs: MetricAttrs, /) -> None:
        return None


class _ObserverSlot:
    """The sink in force. The host may replace it once."""

    def __init__(self) -> None:
        self.observer: Observer = NoObserver()


_slot = _ObserverSlot()


def set_observer(observer: Observer) -> None:
    """Report to the host's instruments instead of dropping the numbers."""
    _slot.observer = observer


def get_observer() -> Observer:
    """The sink in force for this process."""
    return _slot.observer
