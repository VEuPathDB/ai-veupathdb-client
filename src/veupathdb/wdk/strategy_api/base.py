from collections.abc import Sequence

from veupathdb.domain.parameters.phyletic import (
    census_states,
    encode_profile_pattern,
    sort_profile_pattern,
    validate_phyletic_codes,
)
from veupathdb.errors import validate_response
from veupathdb.json_types import JSONObject
from veupathdb.logging import get_logger
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.param_utils import normalize_param_value
from veupathdb.wdk.phyletic_tree import phyletic_tree_of
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
        self._boolean_search_cache: dict[str, str] = {}
        self._answer_param_cache: dict[str, set[str]] = {}

    def _normalize_parameters(self, parameters: JSONObject) -> dict[str, str]:
        """Normalize parameters to WDK string values; drop ``None``.

        ``None`` values are dropped (caller never set them). Every other
        value is coerced via :func:`normalize_param_value`. Empty strings
        are preserved: callers pass them explicitly (e.g. AnswerParams
        that WDK requires as ``""``) and WDK accepts them via
        ``allowEmptyValue``.
        """
        out: dict[str, str] = {
            key: normalize_param_value(value)
            for key, value in (parameters or {}).items()
            if value is not None
        }
        if "profile_pattern" in out:
            out["profile_pattern"] = sort_profile_pattern(out["profile_pattern"])
        return out

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

    async def _expand_profile_pattern_groups(
        self,
        record_type: str,
        pattern: str,
    ) -> str:
        """Expand clade codes in a profile_pattern to their leaf species codes.

        The pattern is matched via SQL LIKE against a census that holds only
        leaf species codes, so a clade code never matches and the search
        silently returns 0. An explicit species overrides the clade above it.

        Raises ``ValidationError`` when the value is not a census pattern,
        states one code twice, or names a code the phyletic tree does not carry.
        """
        states = census_states(pattern)
        if not states:
            return pattern

        response = await self.client.get_search_details(
            record_type, "GenesByOrthologPattern", expand_params=True
        )
        tree = phyletic_tree_of(response.search_data.parameters or [])
        if tree is None:
            logger.debug("The phyletic tree is unreadable; the pattern stands")
            return encode_profile_pattern(states)
        validate_phyletic_codes(list(states), {node.code for node in tree.nodes()})
        return encode_profile_pattern(
            tree.leaf_states(
                [code for code, s in states.items() if s == "include"],
                [code for code, s in states.items() if s == "exclude"],
            )
        )

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
