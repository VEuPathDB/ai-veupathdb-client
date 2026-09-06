"""Core report and answer methods for the Strategy API.

Provides :class:`ReportsMixin` with methods to run reports, fetch step
answers and records, and get step counts.
"""

from pydantic import JsonValue

from veupathdb.json_types import JSONObject
from veupathdb.wdk.strategy_api.base import StrategyAPIBase
from veupathdb.wdk.wdk_models import WDKAnswer, WDKSortSpec


class ReportsMixin(StrategyAPIBase):
    """Mixin providing report, answer, and step count methods."""

    async def run_step_report(
        self,
        step_id: int,
        report_name: str,
        config: JSONObject | None = None,
        user_id: str | None = None,
    ) -> JsonValue:
        """Run a report on a step."""
        uid = await self._get_user_id(user_id)
        # reportConfig is a nested JSONObject, which is valid JsonValue
        report_config: JsonValue = config or {}
        payload: JSONObject = {"reportConfig": report_config}
        return await self.client.run_step_report(uid, step_id, report_name, payload)

    async def get_step_answer(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        user_id: str | None = None,
    ) -> WDKAnswer:
        """Get answer records for a step via the standard report endpoint.

        Convenience wrapper around :meth:`get_step_records`.

        :param step_id: Step ID.
        :param attributes: Attributes to include in response.
        :param pagination: Offset and numRecords.
        :returns: Validated WDK answer with records.
        """
        return await self.get_step_records(
            step_id, attributes=attributes, pagination=pagination, user_id=user_id
        )

    async def get_step_records(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        tables: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        sorting: list[WDKSortSpec] | None = None,
        user_id: str | None = None,
    ) -> WDKAnswer:
        """Get paginated records for a step with configurable attributes and sorting.

        :param step_id: WDK step ID (must be part of a strategy).
        :param attributes: Attribute names to include.
        :param tables: Table names to include.
        :param pagination: ``{offset, numRecords}`` for server-side paging.
        :param sorting: Typed sort specs (attributeName + direction).
        :returns: Validated WDK answer with ``records`` and ``meta``.
        """
        report_config: dict[str, object] = {}
        if attributes:
            report_config["attributes"] = attributes
        if tables:
            report_config["tables"] = tables
        if pagination:
            report_config["pagination"] = pagination
        if sorting:
            report_config["sorting"] = [s.model_dump(by_alias=True) for s in sorting]

        uid = await self._get_user_id(user_id)
        return await self._standard_report(step_id, report_config, user_id=uid)

    async def get_step_count(self, step_id: int, user_id: str | None = None) -> int:
        """Get result count for a step."""
        uid = await self._get_user_id(user_id)
        answer = await self._standard_report(
            step_id, {"pagination": {"offset": 0, "numRecords": 0}}, user_id=uid
        )
        return answer.meta.records_returned()
