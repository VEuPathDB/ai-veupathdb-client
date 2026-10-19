"""Search and record-type endpoint methods for VEuPathDBClient."""

import contextlib
from collections.abc import Iterator, Sequence
from contextvars import ContextVar
from dataclasses import dataclass

import pydantic
from pydantic import JsonValue, TypeAdapter

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters.values import FilterTermClause
from veupathdb.errors import DataParsingError, VEuPathDBError, validate_response
from veupathdb.json_types import JSONObject
from veupathdb.logging import get_logger
from veupathdb.wdk._helpers import _validate_list
from veupathdb.wdk.ai_expression import (
    AI_EXPRESSION_REPORT_PATH,
    AiExpressionReport,
    AiExpressionReportConfig,
)
from veupathdb.wdk.tree_leaves import holds_a_term_list, leaves_of_tree_values
from veupathdb.wdk.wdk_models import (
    WDKAnswer,
    WDKColumnDistribution,
    WDKFilterValue,
    WDKOntologyTermSummary,
    WDKRecordType,
    WDKSearch,
    WDKSearchConfig,
    WDKSearchResponse,
)
from veupathdb.wdk.wdk_parameters import WDKParameter

logger = get_logger(__name__)

_SEARCH_ADAPTER: TypeAdapter[WDKSearch] = TypeAdapter(WDKSearch)
_RECORD_TYPE_ADAPTER: TypeAdapter[WDKRecordType] = TypeAdapter(WDKRecordType)
_PARAMETER_ADAPTER: TypeAdapter[WDKParameter] = TypeAdapter(WDKParameter)

type _DefinitionKey = tuple[str, str | None, str, str, bool]

_read_definitions: ContextVar[dict[_DefinitionKey, WDKSearchResponse] | None] = (
    ContextVar("read_search_definitions", default=None)
)


@contextlib.contextmanager
def search_definitions_read_once() -> Iterator[None]:
    if _read_definitions.get() is not None:
        yield
        return
    reset = _read_definitions.set({})
    try:
        yield
    finally:
        _read_definitions.reset(reset)


@dataclass(frozen=True)
class BooleanSearch:
    search_name: str
    left_param: str
    right_param: str
    operator_param: str


def _named(params: Sequence[str], prefix: str, record_type: str) -> str:
    found = next((p for p in params if p.startswith(prefix)), None)
    if found is None:
        msg = (
            f"Boolean param {prefix} not found for record type '{record_type}' "
            f"(params={list(params)})"
        )
        raise DataParsingError(msg)
    return found


class SearchEndpoints:
    """The search and record-type WDK endpoints. This mixin needs the HTTP client that
    supplies the get and post methods."""

    base_url: str
    _boolean_searches: dict[str, BooleanSearch]

    async def get(self, path: str, params: JSONObject | None = None) -> JsonValue:
        """The HTTP client supplies this method at runtime."""
        raise NotImplementedError  # pragma: no cover

    async def post(
        self,
        path: str,
        json: object = None,
        params: JSONObject | None = None,
        *,
        budget_seconds: float | None = None,
    ) -> JsonValue:
        """The HTTP client supplies this method at runtime."""
        raise NotImplementedError  # pragma: no cover

    async def get_record_types(self, *, expanded: bool = False) -> list[WDKRecordType]:
        """Returns the available record types.

        A plain response holds names only. An expanded response holds objects, and an
        item that fails validation is skipped.
        """
        params: JSONObject | None = {"format": "expanded"} if expanded else None
        raw = await self.get("/record-types", params=params)
        if not isinstance(raw, list):
            return []
        results: list[WDKRecordType] = []
        for item in raw:
            if isinstance(item, str):
                results.append(WDKRecordType(url_segment=item, display_name=item))
            else:
                with contextlib.suppress(pydantic.ValidationError):
                    results.append(_RECORD_TYPE_ADAPTER.validate_python(item))
        return results

    async def get_searches(self, record_type: str) -> list[WDKSearch]:
        """Returns the searches for a record type."""
        raw = await self.get(f"/record-types/{record_type}/searches")
        return _validate_list(raw, _SEARCH_ADAPTER)

    async def boolean_search(self, record_type: str) -> BooleanSearch:
        held = self._boolean_searches.get(record_type)
        if held is not None:
            return held
        name = next(
            (
                search.url_segment
                for search in await self.get_searches(record_type)
                if search.url_segment.startswith("boolean_question")
            ),
            None,
        )
        if name is None:
            msg = f"No boolean combine search found for record type '{record_type}'"
            raise DataParsingError(msg)
        params = (
            await self.get_search_details(record_type, name)
        ).search_data.param_names
        found = BooleanSearch(
            search_name=name,
            left_param=_named(params, "bq_left_op", record_type),
            right_param=_named(params, "bq_right_op", record_type),
            operator_param=_named(params, "bq_operator", record_type),
        )
        self._boolean_searches[record_type] = found
        return found

    async def get_search_details(
        self,
        record_type: str,
        search_name: str,
        *,
        expand_params: bool = True,
    ) -> WDKSearchResponse:
        """Returns the full search configuration, including its parameters."""
        held = _read_definitions.get()
        key: _DefinitionKey = (
            self.base_url,
            veupathdb_auth_token_ctx.get(),
            record_type,
            search_name,
            expand_params,
        )
        if held is not None and key in held:
            return held[key]
        params: JSONObject | None = {"expandParams": "true"} if expand_params else None
        raw = await self.get(
            f"/record-types/{record_type}/searches/{search_name}",
            params=params,
        )
        details = validate_response(
            WDKSearchResponse,
            raw,
            f"WDK search response for {record_type}/{search_name}",
        )
        if held is not None:
            held[key] = details
        return details

    async def expand_tree_params_to_leaves(
        self,
        record_type: str,
        search_name: str,
        params: dict[str, str],
    ) -> dict[str, str]:
        """The parameters with each parent term of a countOnlyLeaves tree as its leaves.

        When the search read fails, the values go unchanged and WDK judges them.
        A configuration with no term list names no tree parent and reads nothing.
        """
        if not holds_a_term_list(params):
            return params
        try:
            response = await self.get_search_details(
                record_type, search_name, expand_params=True
            )
        except VEuPathDBError:
            logger.debug("Failed to expand tree params (non-fatal)")
            return params
        return leaves_of_tree_values(
            response.search_data.parameters or [], params, search_name
        )

    async def get_search_details_with_params(
        self,
        record_type: str,
        search_name: str,
        context: dict[str, str],
        *,
        expand_params: bool = True,
    ) -> WDKSearchResponse:
        """Returns the search configuration under a parameter context. Every context
        value must already be a WDK-encoded string."""
        params: JSONObject | None = {"expandParams": "true"} if expand_params else None
        raw = await self.post(
            f"/record-types/{record_type}/searches/{search_name}",
            json={"contextParamValues": context},
            params=params,
        )
        return validate_response(
            WDKSearchResponse,
            raw,
            f"WDK search response for {record_type}/{search_name}",
        )

    async def get_refreshed_dependent_params(
        self,
        record_type: str,
        search_name: str,
        param_name: str,
        context: dict[str, str],
    ) -> list[WDKParameter]:
        """Returns the dependent params refreshed under a parameter context. Every
        context value must already be a WDK-encoded string."""
        raw = await self.post(
            f"/record-types/{record_type}/searches/{search_name}/refreshed-dependent-params",
            json={
                "changedParam": {
                    "name": param_name,
                    "value": context.get(param_name, ""),
                },
                "contextParamValues": context,
            },
        )
        return _validate_list(raw, _PARAMETER_ADAPTER)

    async def get_ontology_term_summary(
        self,
        record_type: str,
        search_name: str,
        param_name: str,
        ontology_id: str,
        context: dict[str, str],
        *,
        filters: Sequence[FilterTermClause] = (),
    ) -> WDKOntologyTermSummary:
        """Returns the count of each value of one ontology term of a filter parameter.

        Matches WDK's ``QuestionService.getFilterParamOntologyTermSummary``. Every
        context value must already be a WDK-encoded string. ``filters`` are the
        clauses the filtered counts are taken under.
        """
        raw = await self.post(
            f"/record-types/{record_type}/searches/{search_name}/{param_name}/ontology-term-summary",
            json={
                "ontologyId": ontology_id,
                "filters": [
                    clause.model_dump(by_alias=True, mode="json") for clause in filters
                ],
                "contextParamValues": context,
            },
        )
        return validate_response(
            WDKOntologyTermSummary,
            raw,
            f"WDK ontology term summary for {search_name}/{param_name}/{ontology_id}",
        )

    async def run_search_report(
        self,
        record_type: str,
        search_name: str,
        search_config: WDKSearchConfig,
        report_config: JSONObject | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
        budget_seconds: float | None = None,
    ) -> WDKAnswer:
        """Runs a report on a search and creates no step or strategy. The endpoint
        needs no user session, so several calls can run in parallel. A tree value
        goes as its leaves, as ``create_step`` sends it.

        :param view_filters: View filters, sent beside ``reportConfig``.
        :param budget_seconds: How long the report may take once it is sent.
            Time spent waiting for a search slot does not count.
        """
        parameters = await self.expand_tree_params_to_leaves(
            record_type, search_name, dict(search_config.parameters)
        )
        sent = search_config.model_copy(update={"parameters": parameters})
        payload: JSONObject = {
            "searchConfig": sent.model_dump(by_alias=True, exclude_defaults=True),
            "reportConfig": report_config or {},
        }
        if view_filters is not None:
            payload["viewFilters"] = [
                f.model_dump(by_alias=True, mode="json") for f in view_filters
            ]
        result = await self.post(
            f"/record-types/{record_type}/searches/{search_name}/reports/standard",
            json=payload,
            budget_seconds=budget_seconds,
        )
        return validate_response(
            WDKAnswer, result, f"WDK answer for {record_type}/{search_name}"
        )

    async def run_search_column_report(
        self,
        record_type: str,
        search_name: str,
        search_config: WDKSearchConfig,
        column: str,
        *,
        budget_seconds: float | None = None,
    ) -> WDKColumnDistribution:
        """Counts the search's records by each value of one column, with the
        site's ``byValue`` column reporter. It creates no step, and the search
        config's column filters apply first. A tree value goes as its leaves.

        :param budget_seconds: How long the report may take once it is sent.
        """
        parameters = await self.expand_tree_params_to_leaves(
            record_type, search_name, dict(search_config.parameters)
        )
        sent = search_config.model_copy(update={"parameters": parameters})
        result = await self.post(
            f"/record-types/{record_type}/searches/{search_name}"
            f"/columns/{column}/reports/byValue",
            json={
                "searchConfig": sent.model_dump(by_alias=True, exclude_defaults=True),
                "reportConfig": {},
            },
            budget_seconds=budget_seconds,
        )
        return validate_response(
            WDKColumnDistribution,
            result,
            f"WDK column report for {record_type}/{search_name}/{column}",
        )

    async def get_ai_expression_report(self, primary_keys: str) -> AiExpressionReport:
        """Read the site's AI expression summary for one gene record.

        ``primary_keys`` is the gene record's primary key as WDK writes it:
        the source id and the project id, comma separated. The request never
        asks the site to generate a summary, so a gene with nothing cached
        answers with its status and no summary.
        """
        payload: JSONObject = {
            "searchConfig": WDKSearchConfig(
                parameters={"primaryKeys": primary_keys}
            ).model_dump(by_alias=True, exclude_defaults=True),
            "reportConfig": AiExpressionReportConfig().model_dump(by_alias=True),
        }
        raw = await self.post(AI_EXPRESSION_REPORT_PATH, json=payload)
        return validate_response(
            AiExpressionReport, raw, f"WDK aiExpression report for {primary_keys}"
        )
