"""CRUD over the persisted analysis document, the SSOT for one analysis."""

from __future__ import annotations

from pydantic import TypeAdapter

from veupathdb.eda.client import EdaClient
from veupathdb.eda.models import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaAnalysisSummary,
    EdaCreateAnalysisResponse,
    EdaNewAnalysis,
)
from veupathdb.errors import WDKLoginRequiredError
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.helpers import (
    resolve_wdk_user_id,
)

ANALYSIS_SUMMARIES: TypeAdapter[list[EdaAnalysisSummary]] = TypeAdapter(
    list[EdaAnalysisSummary],
)


class EdaAnalysesClient:
    """One project's analysis store for one user."""

    def __init__(self, *, client: EdaClient, project_id: str) -> None:
        self._client = client
        self._project_id = project_id

    async def resolve_user_id(self, wdk_client: VEuPathDBClient) -> str:
        """The numeric WDK user id the analysis routes are keyed by."""
        user_id = await resolve_wdk_user_id(wdk_client)
        if user_id is None:
            raise WDKLoginRequiredError
        return user_id

    def _root(self, user_id: str) -> str:
        return f"/users/{user_id}/analyses/{self._project_id}"

    @property
    def project_id(self) -> str:
        return self._project_id

    async def list_all(self, *, user_id: str) -> list[EdaAnalysisSummary]:
        raw = await self._client.request_json("GET", self._root(user_id))
        return ANALYSIS_SUMMARIES.validate_python(raw)

    async def create(
        self,
        *,
        user_id: str,
        analysis: EdaNewAnalysis,
    ) -> EdaCreateAnalysisResponse:
        raw = await self._client.request_json(
            "POST",
            self._root(user_id),
            json=analysis.model_dump(by_alias=True, mode="json", exclude_none=True),
        )
        return EdaCreateAnalysisResponse.model_validate(raw)

    async def get(self, *, user_id: str, analysis_id: str) -> EdaAnalysisDetail:
        raw = await self._client.request_json(
            "GET", f"{self._root(user_id)}/{analysis_id}"
        )
        return EdaAnalysisDetail.model_validate(raw)

    async def patch_descriptor(
        self,
        *,
        user_id: str,
        analysis_id: str,
        descriptor: EdaAnalysisDescriptor,
    ) -> None:
        await self._client.request_json(
            "PATCH",
            f"{self._root(user_id)}/{analysis_id}",
            json={
                "descriptor": descriptor.model_dump(
                    by_alias=True, mode="json", exclude_none=True
                )
            },
        )

    async def delete(self, *, user_id: str, analysis_id: str) -> None:
        await self._client.request_json(
            "DELETE", f"{self._root(user_id)}/{analysis_id}"
        )
