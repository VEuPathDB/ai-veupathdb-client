"""Search reference value object."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchContext:
    """Immutable reference to a WDK search at a specific site.

    Bundles the (site_id, record_type, search_name) triplet that is passed
    throughout the catalog service, transport, and AI tool layers.
    """

    site_id: str
    record_type: str
    search_name: str
