"""Strategy CRUD methods for the Strategy API."""

import pydantic
from pydantic import TypeAdapter, ValidationError

from veupathdb.errors import validate_response
from veupathdb.json_types import JSONObject
from veupathdb.logging import get_logger
from veupathdb.wdk._helpers import _validate_list
from veupathdb.wdk.strategy_api.base import StrategyAPIBase
from veupathdb.wdk.strategy_api.helpers import (
    tag_internal_wdk_strategy_name,
)
from veupathdb.wdk.wdk_base import WDKModel
from veupathdb.wdk.wdk_models import (
    WDKIdentifier,
    WDKStepTree,
    WDKStrategyDetails,
    WDKStrategySummary,
)

logger = get_logger(__name__)

_STRATEGY_SUMMARY_ADAPTER: TypeAdapter[WDKStrategySummary] = TypeAdapter(
    WDKStrategySummary
)


class _DuplicatedStepTreeResponse(WDKModel):
    """Wrapper for the ``duplicated-step-tree`` endpoint response.

    WDK wraps the step tree in a ``{"stepTree": ...}`` envelope.
    """

    step_tree: WDKStepTree


class StrategiesMixin(StrategyAPIBase):
    """Mixin providing strategy CRUD methods."""

    async def create_strategy(  # noqa: PLR0913
        self,
        step_tree: WDKStepTree,
        name: str,
        description: str | None = None,
        *,
        is_public: bool = False,
        is_saved: bool = False,
        is_internal: bool = False,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        """Create a strategy from a step tree.

        An internal strategy is never public and never saved.
        """
        if is_internal:
            name = tag_internal_wdk_strategy_name(name)
            is_public = False
            is_saved = False

        payload: JSONObject = {
            "name": name,
            "isPublic": is_public,
            "isSaved": is_saved,
            "stepTree": step_tree.model_dump(
                by_alias=True, exclude_none=True, mode="json"
            ),
        }
        if description:
            payload["description"] = description

        logger.info("Creating WDK strategy", name=name)

        uid = await self._get_user_id(user_id)
        raw = await self.client.post(
            f"/users/{uid}/strategies",
            json=payload,
            idempotent=False,
        )
        return WDKIdentifier.model_validate(raw)

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        """Get a strategy by ID."""
        uid = await self._get_user_id(user_id)
        raw = await self.client.get(f"/users/{uid}/strategies/{strategy_id}")
        return validate_response(
            WDKStrategyDetails, raw, f"WDK strategy response for {strategy_id}"
        )

    async def list_strategies(
        self, user_id: str | None = None
    ) -> list[WDKStrategySummary]:
        """List strategies for the current user."""
        uid = await self._get_user_id(user_id)
        raw = await self.client.get(f"/users/{uid}/strategies")
        return _validate_list(raw, _STRATEGY_SUMMARY_ADAPTER)

    async def list_public_strategies(self) -> list[WDKStrategySummary]:
        """List all public strategies from WDK.

        The endpoint needs no authentication.
        """
        adapter = pydantic.TypeAdapter(list[WDKStrategySummary])
        raw = await self.client.get("/strategy-lists/public")
        try:
            return adapter.validate_python(raw)
        except pydantic.ValidationError:
            logger.warning("Failed to parse public strategies response")
            return []

    async def update_strategy(
        self,
        strategy_id: int,
        step_tree: WDKStepTree | None = None,
        name: str | None = None,
        user_id: str | None = None,
    ) -> WDKStrategyDetails:
        """Update a strategy."""
        uid = await self._get_user_id(user_id)

        if step_tree is not None:
            await self.client.put(
                f"/users/{uid}/strategies/{strategy_id}/step-tree",
                json={
                    "stepTree": step_tree.model_dump(
                        by_alias=True, exclude_none=True, mode="json"
                    )
                },
            )

        if name:
            await self.client.patch(
                f"/users/{uid}/strategies/{strategy_id}",
                json={"name": name},
            )

        return await self.get_strategy(strategy_id, user_id=user_id)

    async def set_saved(
        self, strategy_id: int, *, is_saved: bool, user_id: str | None = None
    ) -> None:
        """Set the isSaved flag on a WDK strategy (draft vs saved)."""
        uid = await self._get_user_id(user_id)
        await self.client.patch(
            f"/users/{uid}/strategies/{strategy_id}",
            json={"isSaved": is_saved},
        )

    async def delete_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> None:
        """Delete a strategy."""
        uid = await self._get_user_id(user_id)
        await self.client.delete(f"/users/{uid}/strategies/{strategy_id}")

    async def get_duplicated_step_tree(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStepTree:
        """Get a duplicated step tree for a strategy.

        WDK wraps the tree in a ``stepTree`` envelope, which this unwraps.
        """
        uid = await self._get_user_id(user_id)
        raw = await self.client.post(
            f"/users/{uid}/strategies/{strategy_id}/duplicated-step-tree",
            json={},
        )
        try:
            return _DuplicatedStepTreeResponse.model_validate(raw).step_tree
        except ValidationError:
            return WDKStepTree.model_validate(raw)
