"""Async HTTP client for one site's EDA service."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Literal

import httpx
from pydantic import JsonValue, TypeAdapter

from veupathdb.auth_context import resolve_veupathdb_auth_token
from veupathdb.eda.errors import eda_failure
from veupathdb.eda.models import (
    EdaBinSpec,
    EdaComputeJob,
    EdaCountResponse,
    EdaDifferentialExpressionConfig,
    EdaDistributionResponse,
    EdaFilter,
    EdaPermissionEntry,
    EdaPermissionsResponse,
    EdaStudiesResponse,
    EdaStudyDetail,
    EdaStudyDetailResponse,
    EdaStudyOverview,
    VolcanoStatsResponse,
)
from veupathdb.errors import WDKLoginRequiredError

FILTERS: TypeAdapter[list[EdaFilter]] = TypeAdapter(list[EdaFilter])
JSON_BODY: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

# Content negotiation is one exact string comparison; any other value is TSV.
_JSON_ONLY = "application/json"

_FIRST_ERROR_STATUS = 400


class EdaClient:
    """One site's EDA service. The request's own registered token authenticates it."""

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
                    headers={"Content-Type": _JSON_ONLY},
                )
            return self._client

    def _token(self) -> str:
        token = resolve_veupathdb_auth_token(self.auth_token)
        if not token:
            raise WDKLoginRequiredError
        return token

    async def request_json(
        self,
        method: Literal["GET", "POST", "PATCH", "DELETE"],
        path: str,
        *,
        json: JsonValue | None = None,
        params: dict[str, str] | None = None,
    ) -> JsonValue:
        client = await self._http()
        request = client.build_request(
            method,
            path,
            json=json,
            params=params,
            headers={"Accept": _JSON_ONLY, "Cookie": f"Authorization={self._token()}"},
        )
        response = await client.send(request)
        if response.status_code >= _FIRST_ERROR_STATUS:
            raise eda_failure(method, path, response.status_code, response.text)
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
        body: dict[str, JsonValue] = {
            "filters": _filters(filters),
            "valueSpec": "count",
        }
        # A binSpec is required for a continuous variable and refused otherwise.
        if bin_spec is not None:
            body["binSpec"] = bin_spec.model_dump(
                by_alias=True, mode="json", exclude_none=True
            )
        raw = await self.request_json(
            "POST",
            f"/studies/{study_id}/entities/{entity_id}"
            f"/variables/{variable_id}/distribution",
            json=body,
        )
        return EdaDistributionResponse.model_validate(raw)

    async def submit_compute(
        self,
        *,
        compute_name: str,
        study_id: str,
        config: EdaDifferentialExpressionConfig,
        filters: Sequence[EdaFilter],
        autostart: bool = True,
    ) -> EdaComputeJob:
        raw = await self.request_json(
            "POST",
            f"/computes/{compute_name}",
            json=_compute_body(study_id, config, filters),
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
        config: EdaDifferentialExpressionConfig,
        filters: Sequence[EdaFilter],
    ) -> VolcanoStatsResponse:
        raw = await self.request_json(
            "POST",
            f"/computes/{compute_name}/statistics",
            json=_compute_body(study_id, config, filters),
        )
        return VolcanoStatsResponse.model_validate(raw)


def _filters(filters: Sequence[EdaFilter]) -> JsonValue:
    dumped: JsonValue = FILTERS.dump_python(list(filters), by_alias=True, mode="json")
    return dumped


def _compute_body(
    study_id: str,
    config: EdaDifferentialExpressionConfig,
    filters: Sequence[EdaFilter],
) -> dict[str, JsonValue]:
    """The submit body addresses the job, so a reader sends the same one."""
    return {
        "studyId": study_id,
        "filters": _filters(filters),
        "derivedVariables": [],
        "config": config.model_dump(by_alias=True, mode="json", exclude_none=True),
    }
