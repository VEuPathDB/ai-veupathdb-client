"""Step filter operations for the Strategy API.

WDK has no dedicated filter endpoint. A step's filters live in
``searchConfig.filters`` and are read and written through the step resource.
``viewFilters`` and ``columnFilters`` are separate mechanisms.
"""

from pydantic import JsonValue

from veupathdb.wdk.strategy_api.base import StrategyAPIBase
from veupathdb.wdk.wdk_models import WDKFilterValue


class StepFilterMixin(StrategyAPIBase):
    """Mixin providing step filter reads and writes via searchConfig.filters."""

    async def set_step_filter(
        self,
        step_id: int,
        filter_name: str,
        value: JsonValue,
        *,
        disabled: bool = False,
        user_id: str | None = None,
    ) -> None:
        """Create or update one named filter on a step.

        The other filters and the rest of the search config are preserved.
        """
        uid = await self._get_user_id(user_id)
        current = await self.client.get_step_filters(uid, step_id)
        updated: list[WDKFilterValue] = [f for f in current if f.name != filter_name]
        new_filter = WDKFilterValue(
            name=filter_name,
            value=value,
            disabled=disabled,
        )
        updated.append(new_filter)
        await self.client.update_step_filters(uid, step_id, updated)
