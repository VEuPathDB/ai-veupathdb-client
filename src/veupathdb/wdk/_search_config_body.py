"""The body a search-config write sends, built from a whole search config."""

from veupathdb.json_types import JSONObject
from veupathdb.wdk.wdk_models import WDKSearchConfig


def search_config_write_body(config: WDKSearchConfig) -> JSONObject:
    """Every key the endpoint reads, since it resets each key the body omits.

    ``viewFilters`` is not part of a search config, and WDK's schema rejects it.
    """
    body: JSONObject = config.model_dump(
        by_alias=True, exclude_none=True, exclude={"view_filters"}
    )
    body["filters"] = [f.model_dump(by_alias=True) for f in config.filters]
    return body
