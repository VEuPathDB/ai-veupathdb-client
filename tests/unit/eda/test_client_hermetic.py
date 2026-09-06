"""Subsetting, distributions and computes over the recorded EDA wire."""

from __future__ import annotations

import json

import httpx
import pytest
from tests.unit.eda._hermetic import (
    de_config,
    eda_client,
    fixture,
    registered_token,
    species_filter,
)

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda.errors import (
    EdaBadRequestError,
    EdaForbiddenError,
    EdaInvalidInputError,
)
from veupathdb.eda.models import EdaBinSpec
from veupathdb.errors import WDKLoginRequiredError

pytestmark = pytest.mark.asyncio

__all__ = ["registered_token"]


async def test_the_request_carries_the_authorization_cookie() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("studies_list.json"))

    token = veupathdb_auth_token_ctx.set("token-abc")
    try:
        client = eda_client(httpx.MockTransport(handler))
        await client.list_studies()
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()

    assert "Authorization=token-abc" in seen[0].headers["cookie"]
    assert seen[0].url.path == "/eda/studies"


async def test_a_request_with_no_token_never_reaches_the_wire() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"count": 0})

    token = veupathdb_auth_token_ctx.set(None)
    client = eda_client(httpx.MockTransport(handler))
    try:
        with pytest.raises(WDKLoginRequiredError):
            await client.count(study_id="S", entity_id="E", filters=[])
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()

    assert calls == []


async def test_list_studies_parses_the_recorded_catalog() -> None:
    client = eda_client(
        httpx.MockTransport(
            lambda _r: httpx.Response(200, json=fixture("studies_list.json"))
        )
    )
    studies = await client.list_studies()
    await client.close()
    assert studies
    assert any(s.source_type == "user_submitted" for s in studies)


async def test_get_study_unwraps_the_study_envelope() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("study_detail_phenotype.json"))

    client = eda_client(httpx.MockTransport(handler))
    study = await client.get_study("STUDY_53f554ec6a")
    await client.close()
    assert seen[0].url.path == "/eda/studies/STUDY_53f554ec6a"
    assert study.id == "STUDY_53f554ec6a"
    assert study.root_entity.id == "GENE_PHENOTYPE_DATA_ENTITY"


async def test_get_permissions_returns_the_resolution_map() -> None:
    client = eda_client(
        httpx.MockTransport(
            lambda _r: httpx.Response(200, json=fixture("permissions.json"))
        )
    )
    per_dataset = await client.get_permissions()
    await client.close()
    assert per_dataset["DS_53f554ec6a"].study_id == "STUDY_53f554ec6a"


async def test_count_posts_the_filter_array_and_returns_an_int() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"count": 4011})

    client = eda_client(httpx.MockTransport(handler))
    count = await client.count(
        study_id="STUDY_53f554ec6a",
        entity_id="GENE_PHENOTYPE_DATA_ENTITY",
        filters=[species_filter()],
    )
    await client.close()
    assert count == 4011
    assert seen[0] == {
        "filters": [
            {
                "entityId": "GENE_PHENOTYPE_DATA_ENTITY",
                "variableId": "VAR_035294d0",
                "type": "stringSet",
                "stringSet": ["P. berghei"],
            }
        ]
    }


async def test_a_distribution_omits_the_bin_spec_for_a_categorical_variable() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("distribution_categorical.json"))

    client = eda_client(httpx.MockTransport(handler))
    response = await client.distribution(
        study_id="STUDY_53f554ec6a",
        entity_id="GENE_PHENOTYPE_DATA_ENTITY",
        variable_id="VAR_035294d0",
        filters=[],
    )
    await client.close()
    assert seen[0].url.path == (
        "/eda/studies/STUDY_53f554ec6a/entities/GENE_PHENOTYPE_DATA_ENTITY"
        "/variables/VAR_035294d0/distribution"
    )
    assert json.loads(seen[0].content) == {"filters": [], "valueSpec": "count"}
    assert response.statistics.subset_size == 4279
    assert response.histogram[0].bin_label == "P. berghei"
    assert response.histogram[0].value == 4011


async def test_a_distribution_sends_a_bin_spec_when_one_is_given() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=fixture("distribution_categorical.json"))

    client = eda_client(httpx.MockTransport(handler))
    await client.distribution(
        study_id="S",
        entity_id="E",
        variable_id="V",
        filters=[],
        bin_spec=EdaBinSpec(bin_width=7, bin_units="day"),
    )
    await client.close()
    assert seen[0]["binSpec"] == {"binWidth": 7.0, "binUnits": "day"}


async def test_submit_compute_sends_autostart_and_the_study_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("compute_job_lookup.json"))

    client = eda_client(httpx.MockTransport(handler))
    job = await client.submit_compute(
        compute_name="differentialexpression",
        study_id="STUDY_e973eadd57",
        config=de_config(),
        filters=[],
        autostart=False,
    )
    await client.close()
    assert seen[0].url.params["autostart"] == "false"
    body = json.loads(seen[0].content)
    assert body["studyId"] == "STUDY_e973eadd57"
    assert body["filters"] == []
    assert body["derivedVariables"] == []
    assert len(job.job_id) == 32


async def test_a_statistics_read_repeats_the_submit_body_that_addresses_the_job() -> (
    None
):
    """The job id is a hash of this body, so a reader sends the same one."""
    seen: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        if request.url.path.endswith("/statistics"):
            return httpx.Response(200, json=fixture("volcano_statistics.json"))
        return httpx.Response(200, json=fixture("compute_job_lookup.json"))

    client = eda_client(httpx.MockTransport(handler))
    await client.submit_compute(
        compute_name="differentialexpression",
        study_id="STUDY_e973eadd57",
        config=de_config(),
        filters=[species_filter()],
    )
    stats = await client.compute_statistics(
        compute_name="differentialexpression",
        study_id="STUDY_e973eadd57",
        config=de_config(),
        filters=[species_filter()],
    )
    await client.close()
    assert seen[0] == seen[1]
    submitted = json.loads(seen[0])
    assert submitted["filters"] == [
        {
            "entityId": "GENE_PHENOTYPE_DATA_ENTITY",
            "variableId": "VAR_035294d0",
            "type": "stringSet",
            "stringSet": ["P. berghei"],
        }
    ]
    assert stats.effect_size_label == "log2(Fold Change)"
    assert len(stats.statistics) == 201


async def test_get_job_addresses_the_job_by_its_derivable_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=fixture("compute_job_lookup.json"))

    client = eda_client(httpx.MockTransport(handler))
    job = await client.get_job("db04204e5386396e1ca2cb78469ab6fb")
    await client.close()
    assert seen[0].url.path == "/eda/jobs/db04204e5386396e1ca2cb78469ab6fb"
    assert job.status == "complete"


async def test_a_400_becomes_a_bad_request_error() -> None:
    client = eda_client(
        httpx.MockTransport(
            lambda _r: httpx.Response(
                400,
                json={
                    "status": "bad-request",
                    "message": "Variable 'VAR_deadbeef' is not found",
                },
            )
        )
    )
    with pytest.raises(EdaBadRequestError):
        await client.count(study_id="S", entity_id="E", filters=[])
    await client.close()


async def test_a_403_on_a_compute_becomes_forbidden() -> None:
    client = eda_client(
        httpx.MockTransport(
            lambda _r: httpx.Response(403, json={"status": "forbidden"})
        )
    )
    with pytest.raises(EdaForbiddenError):
        await client.submit_compute(
            compute_name="differentialexpression",
            study_id="DS_e973eadd57",
            config=de_config(),
            filters=[],
        )
    await client.close()


async def test_a_422_becomes_invalid_input() -> None:
    client = eda_client(
        httpx.MockTransport(
            lambda _r: httpx.Response(
                422,
                json={
                    "status": "invalid-input",
                    "errors": {"general": [], "byKey": {"config": ["bad enum"]}},
                },
            )
        )
    )
    with pytest.raises(EdaInvalidInputError):
        await client.submit_compute(
            compute_name="differentialexpression",
            study_id="STUDY_x",
            config=de_config(),
            filters=[],
        )
    await client.close()
