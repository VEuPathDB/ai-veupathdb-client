"""VEuPathDB /temporary-results helpers for downloads."""

from veupathdb.logging import get_logger
from veupathdb.wdk.strategy_api.base import StrategyAPIBase
from veupathdb.wdk.wdk_models import (
    WDKAnswer,
    WDKTemporaryResult,
)

logger = get_logger(__name__)


class TemporaryResultsAPI(StrategyAPIBase):
    """API for creating and managing temporary result downloads.

    Inherits session management (``client``, ``_resolved_user_id``,
    ``_ensure_session``) from :class:`StrategyAPIBase`.
    """

    async def create_temporary_result(
        self,
        step_id: int,
        reporter: str = "standard",
        format_config: dict[str, object] | None = None,
        user_id: str | None = None,
    ) -> WDKTemporaryResult:
        """Create a temporary result for download.

        :param step_id: Step ID to export.
        :param reporter: WDK reporter name (standard, fullRecord, etc.).
        :param format_config: Reporter-specific configuration.
        :param user_id: Explicit user ID override, or ``None`` to use resolved.
        :returns: Validated temporary result with ID.
        """
        payload: dict[str, object] = {
            "stepId": step_id,
            # WDK expects "reportName" here; using "reporterName" triggers
            # 400: JSONObject["reportName"] not found.
            "reportName": reporter,
            # WDK requires reportConfig even when empty — omitting it triggers
            # 400: JSONObject["reportConfig"] not found.
            "reportConfig": format_config or {},
        }

        logger.info(
            "Creating temporary result",
            step_id=step_id,
            reporter=reporter,
        )

        await self._get_user_id(user_id)
        raw = await self.client.post("/temporary-results", json=payload)
        return WDKTemporaryResult.model_validate(raw)

    async def get_download_url(
        self,
        step_id: int,
        output_format: str = "csv",
        attributes: list[str] | None = None,
        user_id: str | None = None,
    ) -> str:
        """Get download URL for step results.

        Creates a temporary result via POST, extracts the ``id`` from the
        response, and constructs the download URL:
        ``{base_url}/temporary-results/{id}/result``.

        :param step_id: Step ID.
        :param output_format: Output format (csv, tab, json).
        :param attributes: Attributes to include.
        :param user_id: Explicit user ID override, or ``None`` to use resolved.
        :returns: Download URL.
        """
        format_config: dict[str, object] = {}

        if output_format in {"csv", "tab"}:
            format_config["type"] = "standard"
            format_config["includeHeader"] = True
            format_config["attachmentType"] = "text"
        elif output_format == "json":
            format_config["type"] = "json"

        if attributes:
            format_config["attributes"] = attributes

        result = await self.create_temporary_result(
            step_id=step_id,
            reporter="standard" if output_format in ("csv", "tab") else "fullRecord",
            format_config=format_config,
            user_id=user_id,
        )

        base = self.client.base_url.rstrip("/")
        return f"{base}/temporary-results/{result.id}"

    async def get_step_preview(
        self,
        step_id: int,
        limit: int = 100,
        attributes: list[str] | None = None,
        user_id: str | None = None,
    ) -> WDKAnswer:
        """Get preview of step results.

        :param step_id: Step ID.
        :param limit: Max records to return.
        :param attributes: Attributes to include.
        :param user_id: Explicit user ID override, or ``None`` to use resolved.
        :returns: Validated WDK answer with records.
        """
        report_config: dict[str, object] = {
            "pagination": {
                "offset": 0,
                "numRecords": limit,
            }
        }
        if attributes:
            report_config["attributes"] = attributes

        uid = await self._get_user_id(user_id)
        return await self._standard_report(step_id, report_config, user_id=uid)
