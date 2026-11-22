from collections.abc import Sequence

from veupathdb.errors import validate_response
from veupathdb.logging import get_logger
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.helpers import (
    CURRENT_USER,
    resolve_wdk_user_id,
)
from veupathdb.wdk.wdk_models import WDKAnswer, WDKFilterValue

logger = get_logger(__name__)


class StrategyAPIBase:
    def __init__(self, client: VEuPathDBClient, user_id: str = CURRENT_USER) -> None:
        self.client = client
        self._initial_user_id = user_id
        self._resolved_user_id = user_id
        self._session_initialized = False

    async def _ensure_session(self) -> None:
        """Resolve the concrete user id once, so every later path names it.

        WDK rewrites the ``current`` alias to whichever identity the request
        authenticated as, so a path built on it cannot fail an ownership check.
        A concrete id is a 403 under the wrong token.
        """
        if self._session_initialized:
            return
        if self._initial_user_id == CURRENT_USER:
            resolved = await resolve_wdk_user_id(self.client)
            if resolved:
                logger.info("Resolved WDK user id", resolved_user_id=resolved)
                self._resolved_user_id = resolved
        self._session_initialized = True

    async def _get_user_id(self, user_id: str | None) -> str:
        if user_id is not None:
            return user_id
        await self._ensure_session()
        return self._resolved_user_id

    async def _standard_report(
        self,
        step_id: int,
        report_config: dict[str, object],
        user_id: str | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
    ) -> WDKAnswer:
        """Run the standard report. ``viewFilters`` is read beside ``reportConfig``."""
        uid = await self._get_user_id(user_id)
        body: dict[str, object] = {"reportConfig": report_config}
        if view_filters is not None:
            body["viewFilters"] = [f.model_dump(by_alias=True) for f in view_filters]
        result = await self.client.post(
            f"/users/{uid}/steps/{step_id}/reports/standard", json=body
        )
        return validate_response(
            WDKAnswer, result, f"WDK answer response for step {step_id}"
        )
