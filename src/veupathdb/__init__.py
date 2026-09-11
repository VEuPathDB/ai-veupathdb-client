"""The typed VEuPathDB client: WDK and EDA, and the foundation both rest on."""

from importlib.metadata import version

from veupathdb.json_types import (
    JSONArray,
    JSONObject,
    JSONValue,
)
from veupathdb.logging import get_logger
from veupathdb.observer import (
    NoObserver,
    Observer,
    get_observer,
    set_observer,
)
from veupathdb.settings import (
    DEFAULT_INTERNAL_STRATEGY_NAME_PREFIX,
    DEFAULT_OAUTH_URL,
    VEuPathDBSettings,
    get_veupathdb_settings,
    on_settings_source_change,
    use_veupathdb_settings_source,
    veupathdb_settings_source,
)
from veupathdb.text import strip_html_tags

__version__ = version("veupathdb-py")

__all__ = [
    "DEFAULT_INTERNAL_STRATEGY_NAME_PREFIX",
    "DEFAULT_OAUTH_URL",
    "JSONArray",
    "JSONObject",
    "JSONValue",
    "NoObserver",
    "Observer",
    "VEuPathDBSettings",
    "get_logger",
    "get_observer",
    "get_veupathdb_settings",
    "on_settings_source_change",
    "set_observer",
    "strip_html_tags",
    "use_veupathdb_settings_source",
    "veupathdb_settings_source",
]
