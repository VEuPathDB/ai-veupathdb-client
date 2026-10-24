"""Record type info, single record, and column distribution methods.

Provides :class:`RecordsMixin` with methods for record type metadata,
individual record retrieval, and column value distributions.
"""

from veupathdb.errors import validate_response
from veupathdb.wdk.strategy_api.base import StrategyAPIBase
from veupathdb.wdk.wdk_models import (
    WDKColumnDistribution,
    WDKRecordInstance,
    WDKRecordType,
)


class RecordsMixin(StrategyAPIBase):
    """Mixin providing record type info, single record, and distribution methods."""

    async def get_record_type_info(self, record_type: str) -> WDKRecordType:
        """Get expanded record type info including attributes and tables.

        :param record_type: WDK record type (e.g. "gene").
        :returns: Validated record type metadata with attribute fields.
        """
        await self._ensure_session()
        raw = await self.client.get(
            f"/record-types/{record_type}",
            params={"format": "expanded"},
        )
        return validate_response(
            WDKRecordType, raw, f"WDK record type response for {record_type}"
        )

    async def get_single_record(
        self,
        record_type: str,
        primary_key: list[dict[str, str]],
        *,
        attributes: list[str] | None = None,
        tables: list[str] | None = None,
    ) -> WDKRecordInstance:
        """Fetch a single record by its primary key.

        WDK's ``POST /record-types/{type}/records`` requires ``primaryKey``,
        ``attributes``, and ``tables`` arrays in the request body.  When
        ``attributes`` or ``tables`` are not provided we send empty arrays
        which tells WDK to return the default set.

        :param record_type: WDK record type.
        :param primary_key: List of ``{name, value}`` primary key parts.
        :param attributes: Attribute names to include (empty = default set).
        :param tables: Table names to include (empty = none).
        :returns: Validated record instance with requested attributes/tables.
        """
        payload: dict[str, object] = {
            "primaryKey": primary_key,
            "attributes": attributes or [],
            "tables": tables or [],
        }

        await self._ensure_session()
        raw = await self.client.post(
            f"/record-types/{record_type}/records",
            json=payload,
        )
        return validate_response(
            WDKRecordInstance, raw, f"WDK record response for {record_type}"
        )

    async def get_column_distribution(
        self,
        step_id: int,
        column_name: str,
        *,
        budget_seconds: float | None = None,
    ) -> WDKColumnDistribution:
        """Counts the step's records by each value of one column, with the
        site's ``byValue`` column reporter. A refused or unparseable report
        raises; it never reads as an empty count.

        :param budget_seconds: How long the report may take once it is sent.
        """
        await self._ensure_session()
        result = await self.client.post(
            f"/users/{self._resolved_user_id}/steps/{step_id}"
            f"/columns/{column_name}/reports/byValue",
            json={"reportConfig": {}},
            budget_seconds=budget_seconds,
        )
        return validate_response(
            WDKColumnDistribution,
            result,
            f"WDK column report for step {step_id}/{column_name}",
        )
