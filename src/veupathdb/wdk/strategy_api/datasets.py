"""Dataset creation methods for the Strategy API.

Provides :class:`DatasetsMixin` with a typed ``create_dataset`` method
matching the monorepo's ``DatasetsService.ts``.
"""

from veupathdb.logging import get_logger
from veupathdb.wdk.strategy_api.base import StrategyAPIBase
from veupathdb.wdk.wdk_models import (
    WDKDatasetConfig,
    WDKIdentifier,
)

logger = get_logger(__name__)


class DatasetsMixin(StrategyAPIBase):
    """Mixin providing dataset creation via ``POST /users/{uid}/datasets``."""

    async def create_dataset(
        self,
        config: WDKDatasetConfig,
        user_id: str | None = None,
    ) -> int:
        """Upload a dataset to WDK and return the dataset ID.

        Accepts the full :data:`WDKDatasetConfig` discriminated union
        (``idList``, ``basket``, ``file``, ``strategy``, ``url``).
        Matches monorepo's ``DatasetsService.createDataset → Number``.

        :param config: Typed dataset configuration.
        :param user_id: Explicit user ID override, or ``None`` to use resolved.
        :returns: Integer dataset ID.
        """
        uid = await self._get_user_id(user_id)
        payload = config.model_dump(by_alias=True)
        raw = await self.client.post(f"/users/{uid}/datasets", json=payload)
        result = WDKIdentifier.model_validate(raw)
        logger.info(
            "Created WDK dataset",
            dataset_id=result.id,
            source_type=config.source_type,
        )
        return result.id
