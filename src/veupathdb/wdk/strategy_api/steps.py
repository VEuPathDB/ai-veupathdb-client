"""Step creation, update, and deletion methods for the Strategy API."""

import asyncio
from http import HTTPStatus

from veupathdb.errors import DataParsingError, VEuPathDBError
from veupathdb.json_types import JSONObject
from veupathdb.logging import get_logger
from veupathdb.wdk._search_config_body import search_config_write_body
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

    async def _get_boolean_search_name(self, record_type: str) -> str:
        """Resolve the boolean combine search name for a record type."""
        if record_type in self._boolean_search_cache:
            return self._boolean_search_cache[record_type]

        searches = await self.client.get_searches(record_type)
        for search in searches:
            if search.url_segment.startswith("boolean_question"):
                self._boolean_search_cache[record_type] = search.url_segment
                return search.url_segment

        msg = f"No boolean combine search found for record type '{record_type}'"
        raise DataParsingError(msg)

    async def _get_boolean_param_names(self, record_type: str) -> tuple[str, str, str]:
        """Resolve parameter names for boolean combine search."""
        boolean_search = await self._get_boolean_search_name(record_type)
        response = await self.client.get_search_details(record_type, boolean_search)
        param_names = response.search_data.param_names

        left = next((p for p in param_names if p.startswith("bq_left_op")), None)
        right = next((p for p in param_names if p.startswith("bq_right_op")), None)
        op = next((p for p in param_names if p.startswith("bq_operator")), None)

        if not left or not right or not op:
            msg = (
                f"Boolean param names not found for record type '{record_type}' "
                f"(left={left}, right={right}, op={op}, params={param_names})"
            )
            raise DataParsingError(msg)

        return left, right, op

    async def _get_answer_param_names(
        self,
        record_type: str,
        search_name: str,
    ) -> set[str]:
        """Return the ``input-step`` (AnswerParam) names for a search.

        Results are cached per record type and search name. A failed catalog
        read raises.
        """
        cache_key = f"{record_type}/{search_name}"
        if cache_key in self._answer_param_cache:
            return self._answer_param_cache[cache_key]

        response = await self.client.get_search_details(record_type, search_name)
        params = response.search_data.parameters or []
        names = {p.name for p in params if p.type == "input-step"}
        self._answer_param_cache[cache_key] = names
        return names

    async def _empty_answer_params(
        self,
        record_type: str,
        search_name: str,
        raw_params: JSONObject,
    ) -> JSONObject:
        """Force every ``input-step`` (AnswerParam) of the search to ``""``.

        WDK requires an answer param on a new step to be the empty string; the
        real input is wired through the ``stepTree``. A failed catalog read
        leaves the params as given, because the create endpoint takes no
        record type and the caller's one may not hold the search.
        """
        params: JSONObject = dict(raw_params)
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

    async def _current_answer_params(
        self,
        step: WDKStep,
        record_type: str,
        search_name: str,
        raw_params: JSONObject,
    ) -> JSONObject:
        """The params with every input-step (AnswerParam) at the step's own value.

        A step that holds no value for one raises: WDK refuses any other value.
        """
        answer_param_names = await self._get_answer_param_names(
            record_type, search_name
        )
        held = step.search_config.parameters
        params: JSONObject = dict(raw_params)
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

    async def _prepare_parameters(
        self, raw_params: JSONObject, record_type: str, search_name: str
    ) -> dict[str, str]:
        """Normalize and expand raw parameters into WDK wire values."""
        normalized = self._normalize_parameters(raw_params)

        if search_name == "GenesByOrthologPattern" and "profile_pattern" in normalized:
            normalized["profile_pattern"] = await self._expand_profile_pattern_groups(
                record_type,
                normalized["profile_pattern"],
            )

        # A tree param with countOnlyLeaves=true counts only leaf values; a
        # parent node returns 0 rows.
        return await self._expand_tree_params_to_leaves(
            record_type, search_name, normalized
        )

    async def create_step(
        self,
        spec: NewStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        """Create an unattached step."""
        raw_params = await self._empty_answer_params(
            record_type, spec.search_name, dict(spec.search_config.parameters)
        )
        normalized = await self._prepare_parameters(
            raw_params, record_type, spec.search_name
        )
        search_config = WDKSearchConfig(
            parameters=normalized, wdk_weight=spec.search_config.wdk_weight
        )

        payload: JSONObject = {
            "searchName": spec.search_name,
            "searchConfig": search_config.model_dump(
                by_alias=True, exclude_defaults=True
            ),
        }
        if spec.custom_name:
            payload["customName"] = spec.custom_name

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
        boolean_search = await self._get_boolean_search_name(record_type)
        left_param, right_param, op_param = await self._get_boolean_param_names(
            record_type
        )

        search_config: JSONObject = {
            "parameters": {
                # WDK requires empty operands; inputs are wired via the stepTree.
                left_param: "",
                right_param: "",
                op_param: spec.boolean_operator.value,
            },
        }
        if spec.wdk_weight is not None:
            search_config["wdkWeight"] = spec.wdk_weight
        payload: JSONObject = {
            "searchName": boolean_search,
            "searchConfig": search_config,
        }
        if spec.custom_name:
            payload["customName"] = spec.custom_name

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
        """Create a transform step.

        WDK requires every ``input-step`` (AnswerParam) to be the empty string
        on a new step; the input is wired through the ``stepTree``.
        """
        clean_params = await self._empty_answer_params(
            record_type, spec.search_name, dict(spec.search_config.parameters)
        )

        normalized = await self._prepare_parameters(
            clean_params, record_type, spec.search_name
        )
        search_config = WDKSearchConfig(
            parameters=normalized, wdk_weight=spec.search_config.wdk_weight
        )

        payload: JSONObject = {
            "searchName": spec.search_name,
            "searchConfig": search_config.model_dump(
                by_alias=True, exclude_defaults=True
            ),
        }
        if spec.custom_name:
            payload["customName"] = spec.custom_name

        logger.info(
            "Creating transform step",
            input=input_step_id,
            transform=spec.search_name,
        )
        logger.info(
            "Transform step payload",
            transform=spec.search_name,
            params=normalized,
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
        """Update a step's parameters, and its weight when the caller sets one.

        Endpoint: ``PUT /users/{uid}/steps/{step_id}/search-config``. The
        endpoint resets every key the body omits and refuses a changed input,
        so the write starts from the step's own config: its filters, column
        filters, weight and input-step params. The caller's parameters are
        normalized and expanded as on step creation.
        """
        uid = await self._get_user_id(user_id)
        step = await self.find_step(step_id, uid)

        raw_params = await self._current_answer_params(
            step, record_type, search_name, dict(search_config.parameters)
        )
        parameters = await self._prepare_parameters(
            raw_params, record_type, search_name
        )
        weight = (
            search_config.wdk_weight
            if "wdk_weight" in search_config.model_fields_set
            else step.search_config.wdk_weight
        )
        written = step.search_config.model_copy(
            update={"parameters": parameters, "wdk_weight": weight}
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
