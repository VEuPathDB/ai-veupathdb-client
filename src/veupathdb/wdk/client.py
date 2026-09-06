"""VEuPathDB WDK REST API client — composed from mixins.

Import the client from here:

    from veupathdb.wdk.client import VEuPathDBClient

The class inherits:
- :class:`HTTPClient` — session management, retry logic, ``get``/``post``/``put``/etc.
- :class:`SearchEndpoints` — record-type and search endpoints
- :class:`AnalysisEndpoints` — analysis, step-filter, and report endpoints
"""

from veupathdb.wdk._analyses import AnalysisEndpoints
from veupathdb.wdk._http import HTTPClient
from veupathdb.wdk._searches import SearchEndpoints


class VEuPathDBClient(HTTPClient, SearchEndpoints, AnalysisEndpoints):
    """HTTP client for VEuPathDB WDK REST services.

    Composed from :class:`HTTPClient` (transport), :class:`SearchEndpoints`
    (search/record-type methods), and :class:`AnalysisEndpoints`
    (analysis/filter/report methods).
    """
