"""Search reference value object."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchContext:
    """Immutable reference to a WDK search at a specific site.

    The (site_id, record_type, search_name) triplet that addresses one search.
    """

    site_id: str
    record_type: str
    search_name: str
