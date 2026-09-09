"""VEuPathDB Strategy API package."""

from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.strategy_api.helpers import (
    is_internal_wdk_strategy_name,
    strip_internal_wdk_strategy_name,
    tag_internal_wdk_strategy_name,
)

__all__ = [
    "StrategyAPI",
    "is_internal_wdk_strategy_name",
    "strip_internal_wdk_strategy_name",
    "tag_internal_wdk_strategy_name",
]
