"""Async HTTP client for one site's EDA service."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Literal

import httpx
from pydantic import JsonValue, TypeAdapter

from veupathdb.auth_context import (
    resolve_user_auth_token,
    resolve_veupathdb_auth_token,
)
from veupathdb.eda.errors import eda_failure
from veupathdb.eda.models import (
    EdaBinSpec,
    EdaBoxplotConfig,
    EdaBoxplotResponse,
    EdaComputeConfig,
    EdaComputedVariableMetadata,
    EdaComputeJob,
    EdaContTableResponse,
    EdaCountResponse,
    EdaDistributionResponse,
    EdaFilter,
    EdaModel,
    EdaMosaicConfig,
    EdaPermissionEntry,
    EdaPermissionsResponse,
    EdaScatterplotConfig,
    EdaScatterplotResponse,
    EdaStudiesResponse,
    EdaStudyDetail,
    EdaStudyDetailResponse,
    EdaStudyOverview,
    EdaTwoByTwoConfig,
    EdaTwoByTwoResponse,
    VolcanoStatsResponse,
)
from veupathdb.errors import WDKLoginRequiredError
from veupathdb.settings import user_agent_header

FILTERS: TypeAdapter[list[EdaFilter]] = TypeAdapter(list[EdaFilter])
JSON_BODY: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

# Content negotiation is one exact string comparison; any other value is TSV.
_JSON_ONLY = "application/json"
_TEXT_ONLY = "text/plain"

# The app whose visualizations read the subset alone, with no compute.
_NO_COMPUTE_APP = "pass"

_FIRST_ERROR_STATUS = 400

# Analyses, derived variables and preferences hang off a user.
_USER_PATH_PREFIX = "/users/"


class EdaClient:
    """One site's EDA service.

    A study read may travel as the deployment; a path under ``/users/`` never does.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
        auth_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.auth_token = auth_token
        self._client: httpx.AsyncClient | None = None
        self._transport = transport
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        async with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=httpx.Timeout(self.timeout),
                    transport=self._transport,
                    headers={"Content-Type": _JSON_ONLY, **user_agent_header()},
                )
            return self._client

    def _token(self, path: str) -> str:
        """Only the researcher's own token reaches a path under ``/users/``."""
        if path.startswith(_USER_PATH_PREFIX):
            return resolve_user_auth_token(self.auth_token)
        token = resolve_veupathdb_auth_token(self.auth_token)
        if not token:
            raise WDKLoginRequiredError
        return token

    async def send(
        self,
        method: Literal["GET", "POST", "PATCH", "DELETE"],
        path: str,
        *,
        json: JsonValue | None = None,
        params: dict[str, str] | None = None,
        accept: str = _JSON_ONLY,
    ) -> httpx.Response:
        """One call, raised as an EDA error on any status from 400 up."""
        client = await self._http()
        request = client.build_request(
            method,
            path,
            json=json,
            params=params,
            headers={
                "Accept": accept,
                "Cookie": f"Authorization={self._token(path)}",
            },
        )
        response = await client.send(request)
        if response.status_code >= _FIRST_ERROR_STATUS:
            raise eda_failure(method, path, response.status_code, response.text)
        return response

    async def request_json(
        self,
        method: Literal["GET", "POST", "PATCH", "DELETE"],
        path: str,
        *,
        json: JsonValue | None = None,
        params: dict[str, str] | None = None,
        accept: str = _JSON_ONLY,
    ) -> JsonValue:
        """The body read as JSON whatever content type it was sent with."""
        response = await self.send(
            method, path, json=json, params=params, accept=accept
        )
        if not response.content or not response.text.strip():
            return None
        return JSON_BODY.validate_json(response.content)

    async def list_studies(self) -> list[EdaStudyOverview]:
        raw = await self.request_json("GET", "/studies")
        return EdaStudiesResponse.model_validate(raw).studies

    async def get_study(self, study_id: str) -> EdaStudyDetail:
        raw = await self.request_json("GET", f"/studies/{study_id}")
        return EdaStudyDetailResponse.model_validate(raw).study

    async def get_permissions(self) -> dict[str, EdaPermissionEntry]:
        raw = await self.request_json("GET", "/permissions")
        return EdaPermissionsResponse.model_validate(raw).per_dataset

    async def count(
        self,
        *,
        study_id: str,
        entity_id: str,
        filters: Sequence[EdaFilter],
    ) -> int:
        raw = await self.request_json(
            "POST",
            f"/studies/{study_id}/entities/{entity_id}/count",
            json={"filters": _filters(filters)},
        )
        return EdaCountResponse.model_validate(raw).count

    async def distribution(
        self,
        *,
        study_id: str,
        entity_id: str,
        variable_id: str,
        filters: Sequence[EdaFilter],
        bin_spec: EdaBinSpec | None = None,
    ) -> EdaDistributionResponse:
        raw = await self.request_json(
            "POST",
            f"/studies/{study_id}/entities/{entity_id}"
            f"/variables/{variable_id}/distribution",
            json=distribution_body(filters, bin_spec),
        )
        return EdaDistributionResponse.model_validate(raw)

    async def submit_compute(
        self,
        *,
        compute_name: str,
        study_id: str,
        config: EdaComputeConfig,
        filters: Sequence[EdaFilter],
        autostart: bool = True,
    ) -> EdaComputeJob:
        raw = await self.request_json(
            "POST",
            f"/computes/{compute_name}",
            json=compute_body(study_id, config, filters),
            params={"autostart": "true" if autostart else "false"},
        )
        return EdaComputeJob.model_validate(raw)

    async def get_job(self, job_id: str) -> EdaComputeJob:
        raw = await self.request_json("GET", f"/jobs/{job_id}")
        return EdaComputeJob.model_validate(raw)

    async def compute_statistics(
        self,
        *,
        compute_name: str,
        study_id: str,
        config: EdaComputeConfig,
        filters: Sequence[EdaFilter],
    ) -> VolcanoStatsResponse:
        raw = await self.request_json(
            "POST",
            f"/computes/{compute_name}/statistics",
            json=compute_body(study_id, config, filters),
        )
        return VolcanoStatsResponse.model_validate(raw)

    async def compute_meta(
        self,
        *,
        compute_name: str,
        study_id: str,
        config: EdaComputeConfig,
        filters: Sequence[EdaFilter],
    ) -> EdaComputedVariableMetadata:
        """The variables a completed job generated. The route answers only text."""
        raw = await self.request_json(
            "POST",
            f"/computes/{compute_name}/meta",
            json=compute_body(study_id, config, filters),
            accept=_TEXT_ONLY,
        )
        return EdaComputedVariableMetadata.model_validate(raw)

    async def scatterplot(
        self,
        *,
        app: str,
        study_id: str,
        filters: Sequence[EdaFilter],
        config: EdaScatterplotConfig,
        compute_config: EdaComputeConfig | None = None,
    ) -> EdaScatterplotResponse:
        raw = await self.request_json(
            "POST",
            f"/apps/{app}/visualizations/scatterplot",
            json=visualization_body(study_id, filters, config, compute_config),
        )
        return EdaScatterplotResponse.model_validate(raw)

    async def two_by_two(
        self,
        *,
        study_id: str,
        filters: Sequence[EdaFilter],
        config: EdaTwoByTwoConfig,
    ) -> EdaTwoByTwoResponse:
        raw = await self.request_json(
            "POST",
            f"/apps/{_NO_COMPUTE_APP}/visualizations/twobytwo",
            json=visualization_body(study_id, filters, config),
        )
        return EdaTwoByTwoResponse.model_validate(raw)

    async def contingency_table(
        self,
        *,
        study_id: str,
        filters: Sequence[EdaFilter],
        config: EdaMosaicConfig,
    ) -> EdaContTableResponse:
        raw = await self.request_json(
            "POST",
            f"/apps/{_NO_COMPUTE_APP}/visualizations/conttable",
            json=visualization_body(study_id, filters, config),
        )
        return EdaContTableResponse.model_validate(raw)

    async def boxplot(
        self,
        *,
        study_id: str,
        filters: Sequence[EdaFilter],
        config: EdaBoxplotConfig,
        app: str = _NO_COMPUTE_APP,
        compute_config: EdaComputeConfig | None = None,
    ) -> EdaBoxplotResponse:
        raw = await self.request_json(
            "POST",
            f"/apps/{app}/visualizations/boxplot",
            json=visualization_body(study_id, filters, config, compute_config),
        )
        return EdaBoxplotResponse.model_validate(raw)


def distribution_body(
    filters: Sequence[EdaFilter], bin_spec: EdaBinSpec | None = None
) -> dict[str, JsonValue]:
    """The ``VariableDistributionPostRequest`` of a count distribution."""
    body: dict[str, JsonValue] = {"filters": _filters(filters), "valueSpec": "count"}
    # A binSpec is required for a continuous variable and refused otherwise.
    if bin_spec is not None:
        body["binSpec"] = bin_spec.model_dump(
            by_alias=True, mode="json", exclude_none=True
        )
    return body


def _filters(filters: Sequence[EdaFilter]) -> JsonValue:
    dumped: JsonValue = FILTERS.dump_python(list(filters), by_alias=True, mode="json")
    return dumped


def compute_body(
    study_id: str,
    config: EdaComputeConfig,
    filters: Sequence[EdaFilter],
) -> dict[str, JsonValue]:
    """The submit body addresses the job, so a reader sends the same one."""
    return {
        "studyId": study_id,
        "filters": _filters(filters),
        "derivedVariables": [],
        "config": _config(config),
    }


def visualization_body(
    study_id: str,
    filters: Sequence[EdaFilter],
    config: EdaModel,
    compute_config: EdaComputeConfig | None = None,
) -> dict[str, JsonValue]:
    """A visualization request. Only a compute-backed app takes ``computeConfig``."""
    body: dict[str, JsonValue] = {
        "studyId": study_id,
        "filters": _filters(filters),
        "config": _config(config),
    }
    if compute_config is not None:
        body["computeConfig"] = _config(compute_config)
    return body


def _config(config: EdaModel) -> JsonValue:
    dumped: JsonValue = config.model_dump(by_alias=True, mode="json", exclude_none=True)
    return dumped
