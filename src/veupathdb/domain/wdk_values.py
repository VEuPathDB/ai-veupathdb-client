"""Pure WDK value objects shared across layers.

Record-id parts and column-distribution histogram shapes are referenced by
both the integration response models and the transport DTOs, so they live in
the domain layer (no I/O) to avoid a transport→integration dependency.
"""

from typing import Literal

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from veupathdb.model import CamelModel

WDKSortDirection = Literal["ASC", "DESC"]


class _WDKValue(CamelModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
        frozen=True,
    )


class WDKRecordIdPart(_WDKValue):
    """One (name, value) segment of a WDK record's composite primary key."""

    name: str
    value: str


class WDKHistogramBin(_WDKValue):
    """Single bin in a column distribution histogram."""

    value: int = 0
    bin_start: str = ""
    bin_end: str = ""
    bin_label: str = ""


class WDKHistogramStatistics(_WDKValue):
    """Statistics summary for a column distribution."""

    subset_size: int = 0
    subset_min: float | None = None
    subset_max: float | None = None
    subset_mean: float | None = None
    num_var_values: int = 0
    num_distinct_values: int = 0
    num_distinct_entity_records: int = 0
    num_missing_cases: int = 0
