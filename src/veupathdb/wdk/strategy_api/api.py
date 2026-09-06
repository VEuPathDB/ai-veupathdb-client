"""Composed StrategyAPI class.

Aggregates all strategy API mixins into the final :class:`StrategyAPI` class
that callers instantiate.
"""

from veupathdb.wdk.strategy_api.analyses import AnalysisMixin
from veupathdb.wdk.strategy_api.datasets import DatasetsMixin
from veupathdb.wdk.strategy_api.filters import StepFilterMixin
from veupathdb.wdk.strategy_api.records import RecordsMixin
from veupathdb.wdk.strategy_api.reports import ReportsMixin
from veupathdb.wdk.strategy_api.steps import StepsMixin
from veupathdb.wdk.strategy_api.strategies import (
    StrategiesMixin,
)


class StrategyAPI(
    StepsMixin,
    StrategiesMixin,
    DatasetsMixin,
    ReportsMixin,
    AnalysisMixin,
    StepFilterMixin,
    RecordsMixin,
):
    """API for creating and managing WDK strategies.

    Provides methods to create steps, compose step trees, build strategies,
    create datasets, run reports, manage filters, execute analyses, and
    fetch records. Follows the WDK REST pattern: create unattached steps,
    then POST a strategy with a stepTree linking them.

    Inherits from :class:`StepsMixin`, :class:`StrategiesMixin`,
    :class:`DatasetsMixin`, :class:`ReportsMixin`, :class:`AnalysisMixin`,
    :class:`StepFilterMixin`, :class:`RecordsMixin`, and
    :class:`StrategyAPIBase` (via MRO).
    """
