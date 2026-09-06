"""Step analysis lifecycle for the Strategy API."""

import asyncio
from dataclasses import dataclass

from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb.json_types import JSONObject
from veupathdb.logging import get_logger
from veupathdb.wdk.strategy_api.base import StrategyAPIBase
from veupathdb.wdk.wdk_models import (
    WDKAnalysisStatus,
    WDKStepAnalysisConfig,
    WDKStepAnalysisSummary,
    WDKStepAnalysisType,
    WDKStepAnalysisTypeResponse,
)

logger = get_logger(__name__)


@dataclass
class AnalysisPollConfig:
    """Polling options for a step analysis run."""

    poll_interval: float = 2.0
    max_wait: float = 300.0
    max_retries: int = 3


# A task set keeps each background task alive until it ends.
_background_tasks: set[asyncio.Task[None]] = set()


class AnalysisMixin(StrategyAPIBase):
    """Step analysis lifecycle methods."""

    # WDK re-executes exactly the statuses carrying `requiresRerun`.
    _RETRIABLE_STATUSES = frozenset(
        {"ERROR", "EXPIRED", "INTERRUPTED", "OUT_OF_DATE", "STEP_REVISED"}
    )
    # These two describe a timeout or a shutdown, not the data.
    _RUN_CONDITION_STATUSES = frozenset({"EXPIRED", "INTERRUPTED"})

    async def list_analysis_types(
        self, step_id: int, user_id: str | None = None
    ) -> list[WDKStepAnalysisType]:
        """Lists the analysis types that are available for a step."""
        uid = await self._get_user_id(user_id)
        return await self.client.list_analysis_types(uid, step_id)

    async def get_analysis_type(
        self, step_id: int, analysis_type: str, user_id: str | None = None
    ) -> WDKStepAnalysisTypeResponse:
        """Returns the analysis form metadata for a step."""
        uid = await self._get_user_id(user_id)
        return await self.client.get_analysis_type(uid, step_id, analysis_type)

    async def list_step_analyses(
        self, step_id: int, user_id: str | None = None
    ) -> list[WDKStepAnalysisSummary]:
        """Lists the analyses that already ran on a step."""
        uid = await self._get_user_id(user_id)
        return await self.client.list_step_analyses(uid, step_id)

    async def _warmup_step(self, step_id: int) -> None:
        """Makes WDK compute the answer of a step before an analysis runs.

        WDK runs an analysis only on a step that has a cached answer. A
        report with zero records builds that cache for the step and its inputs.
        """
        logger.info("Warming up step answer", step_id=step_id)
        warmup = await self._standard_report(
            step_id, {"pagination": {"offset": 0, "numRecords": 0}}
        )
        logger.info(
            "Step answer warmed up",
            step_id=step_id,
            total_count=warmup.meta.records_returned(),
        )

    async def _create_analysis(
        self,
        uid: str,
        step_id: int,
        analysis_type: str,
        parameters: JSONObject | None = None,
        custom_name: str | None = None,
    ) -> WDKStepAnalysisConfig:
        """Creates a step analysis instance and returns the config that WDK sends."""
        payload: JSONObject = {
            "analysisName": analysis_type,
            "parameters": parameters or {},
        }
        if custom_name:
            payload["displayName"] = custom_name

        instance = await self.client.create_step_analysis(uid, step_id, payload)

        logger.info(
            "Created step analysis instance",
            step_id=step_id,
            analysis_type=analysis_type,
            analysis_id=instance.analysis_id,
        )
        return instance

    async def _poll_analysis(
        self,
        uid: str,
        step_id: int,
        analysis_id: int,
        poll_interval: float,
        max_wait: float,
        max_retries: int,
    ) -> None:
        """Polls an analysis instance until it completes.

        A retriable status starts a new run. A failure, an expiry or a
        timeout raises an error.
        """
        elapsed = 0.0
        retries = 0
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            status = await self.client.get_analysis_status(uid, step_id, analysis_id)
            logger.debug(
                "Analysis status poll",
                analysis_id=analysis_id,
                status=status,
                elapsed=elapsed,
            )

            if status == "COMPLETE":
                return
            if status in self._RETRIABLE_STATUSES:
                retries += 1
                logger.warning(
                    "Analysis returned retriable status",
                    analysis_id=analysis_id,
                    status=status,
                    retry=retries,
                )
                if retries > max_retries:
                    self._log_analysis_failure(uid, step_id, analysis_id)
                    raise VEuPathDBError(
                        code=VEuPathDBErrorCode.INTERNAL_ERROR,
                        title="Analysis unavailable",
                        status=500,
                        detail=self._give_up_detail(status, retries),
                    )
                # A new run of the same instance resets it to PENDING.
                logger.warning(
                    "Re-running same analysis instance",
                    analysis_id=analysis_id,
                    status=status,
                    retry=retries,
                )
                await self.client.run_analysis_instance(uid, step_id, analysis_id)

        raise VEuPathDBError(
            code=VEuPathDBErrorCode.INTERNAL_ERROR,
            title="Step analysis timed out",
            status=500,
            detail=f"Analysis {analysis_id} did not complete within {max_wait}s",
        )

    @classmethod
    def _give_up_detail(cls, status: str, retries: int) -> str:
        """Explain the give-up in terms of what the status actually reports."""
        attempts = (
            f"VEuPathDB could not complete this analysis "
            f"(returned {status} after {retries} attempts)."
        )
        if status in cls._RUN_CONDITION_STATUSES:
            return (
                f"{attempts} The run was cut short rather than rejected, so the "
                f"same analysis may succeed later."
            )
        return (
            f"{attempts} This typically happens when the gene set is too small "
            f"or lacks the required annotations."
        )

    def _log_analysis_failure(self, uid: str, step_id: int, analysis_id: int) -> None:
        """Logs the details of a failed analysis in the background.

        The fetch errors are logged, not raised.
        """

        async def _fetch_debug_info() -> None:
            try:
                analyses = await self.client.list_step_analyses(uid, step_id)
                logger.error(
                    "Step analyses list on failure",
                    step_id=step_id,
                    analysis_id=analysis_id,
                    analyses=analyses,
                )
            except Exception as exc:
                logger.exception(
                    "Could not list step analyses",
                    error=str(exc),
                )
            try:
                err_result = await self.client.get_analysis_result(
                    uid, step_id, analysis_id
                )
                logger.error(
                    "Analysis error result",
                    analysis_id=analysis_id,
                    error_result=err_result,
                )
            except Exception as exc:
                logger.exception(
                    "Could not fetch analysis result",
                    analysis_id=analysis_id,
                    error=str(exc),
                )

        # The caller does not wait for this task. The set holds the reference.
        task = asyncio.create_task(_fetch_debug_info())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    async def run_step_analysis(
        self,
        step_id: int,
        analysis_type: str,
        parameters: JSONObject | None = None,
        custom_name: str | None = None,
        poll_config: AnalysisPollConfig | None = None,
        user_id: str | None = None,
    ) -> JSONObject:
        """Creates a step analysis, runs it, and waits for the result.

        The step must belong to a strategy. A failure or a timeout raises
        an error.
        """
        uid = await self._get_user_id(user_id)
        cfg = poll_config or AnalysisPollConfig()

        await self._warmup_step(step_id)

        instance = await self._create_analysis(
            uid, step_id, analysis_type, parameters, custom_name
        )
        analysis_id = instance.analysis_id

        await self.client.run_analysis_instance(uid, step_id, analysis_id)

        await self._poll_analysis(
            uid, step_id, analysis_id, cfg.poll_interval, cfg.max_wait, cfg.max_retries
        )

        return await self.client.get_analysis_result(uid, step_id, analysis_id)

    async def get_analysis_status(
        self,
        step_id: int,
        analysis_id: int,
        user_id: str | None = None,
    ) -> WDKAnalysisStatus:
        """Returns the execution status of a step analysis instance."""
        uid = await self._get_user_id(user_id)
        return await self.client.get_analysis_status(uid, step_id, analysis_id)

    async def get_analysis_result(
        self,
        step_id: int,
        analysis_id: int,
        user_id: str | None = None,
    ) -> JSONObject:
        """Returns the result of a completed step analysis instance."""
        uid = await self._get_user_id(user_id)
        return await self.client.get_analysis_result(uid, step_id, analysis_id)
