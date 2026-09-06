"""Search and record-type endpoint methods for VEuPathDBClient."""

import contextlib

import pydantic
from pydantic import JsonValue, TypeAdapter

from veupathdb.errors import validate_response
from veupathdb.json_types import JSONObject
from veupathdb.logging import get_logger
from veupathdb.wdk._helpers import _validate_list
from veupathdb.wdk.ai_expression import (
    AI_EXPRESSION_REPORT_PATH,
    AiExpressionReport,
    AiExpressionReportConfig,
)
from veupathdb.wdk.wdk_models import (
    WDKAnswer,
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


class SearchEndpoints:
    """The search and record-type WDK endpoints. This mixin needs the HTTP client that
    supplies the get and post methods."""

    async def get(self, path: str, params: JSONObject | None = None) -> JsonValue:
        """The HTTP client supplies this method at runtime."""
        raise NotImplementedError  # pragma: no cover

    async def post(
        self,
        path: str,
        json: object = None,
        params: JSONObject | None = None,
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

    async def get_search_details(
        self,
        record_type: str,
        search_name: str,
        *,
        expand_params: bool = True,
    ) -> WDKSearchResponse:
        """Returns the full search configuration, including its parameters."""
        params: JSONObject | None = {"expandParams": "true"} if expand_params else None
        raw = await self.get(
            f"/record-types/{record_type}/searches/{search_name}",
            params=params,
        )
        return validate_response(
            WDKSearchResponse,
            raw,
            f"WDK search response for {record_type}/{search_name}",
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

    async def run_search_report(
        self,
        record_type: str,
        search_name: str,
        search_config: WDKSearchConfig,
        report_config: JSONObject | None = None,
    ) -> WDKAnswer:
        """Runs a report on a search and creates no step or strategy. The endpoint
        needs no user session, so several calls can run in parallel."""
        payload: JSONObject = {
            "searchConfig": search_config.model_dump(
                by_alias=True, exclude_defaults=True
            ),
            "reportConfig": report_config or {},
        }
        result = await self.post(
            f"/record-types/{record_type}/searches/{search_name}/reports/standard",
            json=payload,
        )
        return validate_response(
            WDKAnswer, result, f"WDK answer for {record_type}/{search_name}"
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
