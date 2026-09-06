"""The analysis-document client and the WDK user id it is addressed by."""

from __future__ import annotations

import json

import httpx
import pytest
from tests.unit.eda._hermetic import (
    eda_client,
    registered_token,
    species_filter,
)

from veupathdb.eda.analyses import EdaAnalysesClient
from veupathdb.eda.models import (
    EdaAnalysisDescriptor,
    EdaNewAnalysis,
    EdaSubsetDescriptor,
)
from veupathdb.errors import WDKLoginRequiredError
from veupathdb.wdk.client import VEuPathDBClient

pytestmark = pytest.mark.asyncio

__all__ = ["registered_token"]


async def test_create_analysis_posts_the_new_analysis_under_the_project() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"analysisId": "t4fszEJ"})

    client = eda_client(httpx.MockTransport(handler))
    analyses = EdaAnalysesClient(client=client, project_id="PlasmoDB")
    created = await analyses.create(
        user_id="1216062453",
        analysis=EdaNewAnalysis(study_id="DS_53f554ec6a", display_name="probe"),
    )
    await client.close()
    assert created.analysis_id == "t4fszEJ"
    assert seen[0].url.path == "/eda/users/1216062453/analyses/PlasmoDB"
    body = json.loads(seen[0].content)
    assert body["studyId"] == "DS_53f554ec6a"
    assert body["descriptor"]["subset"]["descriptor"] == []


async def test_patch_descriptor_sends_only_the_descriptor() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    client = eda_client(httpx.MockTransport(handler))
    analyses = EdaAnalysesClient(client=client, project_id="PlasmoDB")
    await analyses.patch_descriptor(
        user_id="1",
        analysis_id="t4fszEJ",
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(descriptor=[species_filter()]),
        ),
    )
    await client.close()
    assert seen[0].method == "PATCH"
    assert seen[0].url.path == "/eda/users/1/analyses/PlasmoDB/t4fszEJ"
    assert set(json.loads(seen[0].content)) == {"descriptor"}


async def test_get_analysis_parses_the_stored_descriptor() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "analysisId": "t4fszEJ",
                "displayName": "probe",
                "studyId": "DS_53f554ec6a",
                "numFilters": 1,
                "descriptor": {
                    "subset": {
                        "descriptor": [
                            {
                                "entityId": "GENE_PHENOTYPE_DATA_ENTITY",
                                "variableId": "VAR_035294d0",
                                "type": "stringSet",
                                "stringSet": ["P. berghei"],
                            }
                        ],
                        "uiSettings": {},
                    }
                },
            },
        )

    client = eda_client(httpx.MockTransport(handler))
    analyses = EdaAnalysesClient(client=client, project_id="PlasmoDB")
    detail = await analyses.get(user_id="1", analysis_id="t4fszEJ")
    await client.close()
    assert seen[0].url.path == "/eda/users/1/analyses/PlasmoDB/t4fszEJ"
    assert detail.num_filters == 1
    assert detail.descriptor.subset.descriptor == [species_filter()]


async def test_list_all_returns_every_analysis_summary() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                {"analysisId": "t4fszEJ", "displayName": "probe"},
                {"analysisId": "kW2n1Qb", "displayName": "second"},
            ],
        )

    client = eda_client(httpx.MockTransport(handler))
    analyses = EdaAnalysesClient(client=client, project_id="PlasmoDB")
    summaries = await analyses.list_all(user_id="1")
    await client.close()
    assert seen[0].url.path == "/eda/users/1/analyses/PlasmoDB"
    assert [s.analysis_id for s in summaries] == ["t4fszEJ", "kW2n1Qb"]


async def test_delete_analysis_addresses_the_single_analysis() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202)

    client = eda_client(httpx.MockTransport(handler))
    analyses = EdaAnalysesClient(client=client, project_id="PlasmoDB")
    await analyses.delete(user_id="1", analysis_id="t4fszEJ")
    await client.close()
    assert seen[0].method == "DELETE"


async def test_resolve_user_id_returns_the_numeric_wdk_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wdk = VEuPathDBClient(base_url="https://plasmodb.org/plasmo/service")
    http = httpx.AsyncClient(
        base_url=wdk.base_url,
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(200, json={"id": 1216062453, "isGuest": False})
        ),
    )

    async def _http() -> httpx.AsyncClient:
        return http

    monkeypatch.setattr(wdk, "_get_client", _http)
    analyses = EdaAnalysesClient(
        client=eda_client(httpx.MockTransport(lambda _r: httpx.Response(204))),
        project_id="PlasmoDB",
    )
    user_id = await analyses.resolve_user_id(wdk)
    await http.aclose()
    assert user_id == "1216062453"


async def test_resolve_user_id_refuses_a_response_that_names_no_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wdk = VEuPathDBClient(base_url="https://plasmodb.org/plasmo/service")
    http = httpx.AsyncClient(
        base_url=wdk.base_url,
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
    )

    async def _http() -> httpx.AsyncClient:
        return http

    monkeypatch.setattr(wdk, "_get_client", _http)
    analyses = EdaAnalysesClient(
        client=eda_client(httpx.MockTransport(lambda _r: httpx.Response(204))),
        project_id="PlasmoDB",
    )
    with pytest.raises(WDKLoginRequiredError):
        await analyses.resolve_user_id(wdk)
    await http.aclose()
