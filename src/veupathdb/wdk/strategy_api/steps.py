"""Step creation, update, and deletion methods for the Strategy API."""

import asyncio
from http import HTTPStatus

from veupathdb.errors import DataParsingError, VEuPathDBError
from veupathdb.logging import get_logger
from veupathdb.wdk._search_config_body import (
    combined_step_body,
    new_step_body,
    search_config_write_body,
)
from veupathdb.wdk.strategy_api.base import StrategyAPIBase
from veupathdb.wdk.wdk_models import (
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
)

logger = get_logger(__name__)


class StepsMixin(StrategyAPIBase):
    """Mixin providing step creation and update methods."""

    async def _get_answer_param_names(
        self,
        record_type: str,
        search_name: str,
    ) -> set[str]:
        """Return the ``input-step`` (AnswerParam) names for a search.

        A failed catalog read raises.
        """
        response = await self.client.get_search_details(record_type, search_name)
        params = response.search_data.parameters or []
        return {p.name for p in params if p.type == "input-step"}

    async def _empty_answer_params(
        self,
        record_type: str,
        search_name: str,
        raw_params: dict[str, str],
    ) -> dict[str, str]:
        """Force every ``input-step`` (AnswerParam) of the search to ``""``.

        WDK requires an answer param on a new step to be the empty string; the
        real input is wired through the ``stepTree``. A failed catalog read
        leaves the params as given, because the create endpoint takes no
        record type and the caller's one may not hold the search.
        """
        params = dict(raw_params)
        try:
            answer_param_names = await self._get_answer_param_names(
                record_type, search_name
            )
        except VEuPathDBError:
            logger.warning(
                "No catalog read of the input params for a new step",
                search_name=search_name,
                record_type=record_type,
            )
            return params
        for ap_name in answer_param_names:
            params[ap_name] = ""
        return params

    async def _with_empty_answer_params(
        self, spec: NewStepSpec, record_type: str
    ) -> NewStepSpec:
        parameters = await self._empty_answer_params(
            record_type, spec.search_name, dict(spec.search_config.parameters)
        )
        return spec.model_copy(
            update={
                "search_config": spec.search_config.model_copy(
                    update={"parameters": parameters}
                )
            }
        )

    async def _current_answer_params(
        self,
        step: WDKStep,
        record_type: str,
        search_name: str,
        raw_params: dict[str, str],
    ) -> dict[str, str]:
        """The params with every input-step (AnswerParam) at the step's own value.

        A step that holds no value for one raises: WDK refuses any other value.
        """
        answer_param_names = await self._get_answer_param_names(
            record_type, search_name
        )
        held = step.search_config.parameters
        params = dict(raw_params)
        for ap_name in sorted(answer_param_names):
            if ap_name not in held:
                msg = f"WDK step {step.id} holds no value for input '{ap_name}'"
                raise DataParsingError(msg)
            params[ap_name] = held[ap_name]
        return params

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        """Fetch a single step by id. Mirrors the monorepo ``findStep``."""
        uid = await self._get_user_id(user_id)
        raw = await self.client.get(f"/users/{uid}/steps/{step_id}")
        return WDKStep.model_validate(raw)

    async def create_step(
        self,
        spec: NewStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        """Create an unattached step, its search config sent as given."""
        payload = new_step_body(await self._with_empty_answer_params(spec, record_type))

        logger.info(
            "Creating WDK step",
            record_type=record_type,
            search_name=spec.search_name,
        )

        uid = await self._get_user_id(user_id)
        raw = await self.client.post(
            f"/users/{uid}/steps",
            json=payload,
            idempotent=False,
        )
        return WDKIdentifier.model_validate(raw)

    async def create_combined_step(
        self,
        spec: CombinedStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        """Create a combined step that applies a boolean operator."""
        uid = await self._get_user_id(user_id)
        boolean = await self.client.boolean_search(record_type)

        payload = combined_step_body(spec, boolean)

        logger.info(
            "Creating combined step",
            primary=spec.primary_step_id,
            secondary=spec.secondary_step_id,
            operator=spec.boolean_operator.value,
        )

        raw = await self.client.post(
            f"/users/{uid}/steps",
            json=payload,
            idempotent=False,
        )
        return WDKIdentifier.model_validate(raw)

    async def create_transform_step(
        self,
        spec: NewStepSpec,
        input_step_id: int,
        record_type: str = "transcript",
        *,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        """Create a transform step, its search config sent as given.

        WDK requires every ``input-step`` (AnswerParam) to be the empty string
        on a new step; the input is wired through the ``stepTree``.
        """
        sent = await self._with_empty_answer_params(spec, record_type)
        payload = new_step_body(sent)

        logger.info(
            "Creating transform step",
            input=input_step_id,
            transform=spec.search_name,
        )
        logger.info(
            "Transform step payload",
            transform=spec.search_name,
            params=sent.search_config.parameters,
        )

        uid = await self._get_user_id(user_id)
        raw = await self.client.post(
            f"/users/{uid}/steps",
            json=payload,
            idempotent=False,
        )
        return WDKIdentifier.model_validate(raw)

    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
        *,
        user_id: str | None = None,
    ) -> None:
        """Update a step's parameters, and its weight and filters when stated.

        Endpoint: ``PUT /users/{uid}/steps/{step_id}/search-config``. The
        endpoint resets every key the body omits and refuses a changed input,
        so the write starts from the step's own config: its filters, column
        filters, weight and input-step params. Stated filters replace the held
        list whole. The caller's parameters are sent as given.
        """
        uid = await self._get_user_id(user_id)
        step = await self.find_step(step_id, uid)

        parameters = await self._current_answer_params(
            step, record_type, search_name, dict(search_config.parameters)
        )
        stated = search_config.model_fields_set
        written = step.search_config.model_copy(
            update={
                "parameters": parameters,
                "wdk_weight": search_config.wdk_weight
                if "wdk_weight" in stated
                else step.search_config.wdk_weight,
                "filters": search_config.filters
                if "filters" in stated
                else step.search_config.filters,
            }
        )

        logger.info(
            "Updating step search config",
            step_id=step_id,
            search_name=search_name,
        )
        await self.client.put(
            f"/users/{uid}/steps/{step_id}/search-config",
            json=search_config_write_body(written),
        )

    async def delete_step(
        self,
        step_id: int,
        *,
        user_id: str | None = None,
    ) -> None:
        """Delete a step. A 404 means the step is already gone."""
        uid = await self._get_user_id(user_id)
        try:
            await self.client.delete(f"/users/{uid}/steps/{step_id}")
        except VEuPathDBError as exc:
            if exc.status == HTTPStatus.NOT_FOUND:
                return
            raise

    async def delete_orphaned_steps(self, step_ids: list[int]) -> list[int]:
        """Delete step rows in parallel and name the ids WDK kept.

        One refusal does not abort the others: the caller decides what to do
        with the leftovers.
        """
        if not step_ids:
            return []

        async def one(step_id: int) -> int | None:
            try:
                await self.delete_step(step_id)
            except VEuPathDBError as exc:
                logger.warning(
                    "Failed to delete orphaned WDK step",
                    step_id=step_id,
                    error=str(exc),
                )
                return step_id
            return None

        results = await asyncio.gather(*(one(step_id) for step_id in step_ids))
        return [step_id for step_id in results if step_id is not None]

    async def update_step_properties(
        self,
        step_id: int,
        spec: PatchStepSpec,
        *,
        user_id: str | None = None,
    ) -> None:
        """Update a step's display properties.

        Endpoint: ``PATCH /users/{uid}/steps/{step_id}``. Unset fields are
        excluded from the payload.
        """
        payload = spec.model_dump(by_alias=True, exclude_none=True, mode="json")

        logger.info(
            "Updating step properties",
            step_id=step_id,
            fields=list(payload.keys()),
        )

        uid = await self._get_user_id(user_id)
        await self.client.patch(
            f"/users/{uid}/steps/{step_id}",
            json=payload,
        )
