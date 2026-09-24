"""What ``eda_capture record`` asks a distribution endpoint, and what it writes."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.devtools.eda_capture import (
    DISTRIBUTION_CAPTURES,
    DistributionCapture,
    EdaFixtureProvenance,
    capture_distribution,
    load_provenance,
    write_distribution,
)
from veupathdb.devtools.eda_schemas import BINDINGS, verify_wire_body
from veupathdb.eda import EdaClient
from veupathdb.json_types import JSONObject
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

_BASE = "https://plasmodb.org/eda"
_SPECIES = {
    "entityId": "GENE_PHENOTYPE_DATA_ENTITY",
    "variableId": "VAR_035294d0",
    "type": "stringSet",
    "stringSet": ["P. berghei"],
}
_SENSE_READS = {
    "entityId": "ENT_fd574cd6",
    "variableId": "SEQUENCE_READ_COUNT_SENSE",
    "type": "numberRange",
    "min": 1000.0,
    "max": 61892.0,
}
_STATISTICS: JSONObject = {
    "subsetSize": 3,
    "numVarValues": 3,
    "numDistinctValues": 3,
    "numDistinctEntityRecords": 3,
    "numMissingCases": 0,
}


@pytest.fixture(autouse=True)
def _service_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    yield
    veupathdb_auth_token_ctx.reset(token)


def _named(name: str) -> DistributionCapture:
    return next(c for c in DISTRIBUTION_CAPTURES if c.name == name)


def _bin(gene: str) -> JSONObject:
    return {"value": 1, "binStart": gene, "binEnd": gene, "binLabel": gene}


def test_each_study_is_read_under_its_example_subset_and_under_none() -> None:
    requests = {
        c.name: (c.site, c.path, c.request_body()) for c in DISTRIBUTION_CAPTURES
    }

    phenotype = (
        "/studies/STUDY_53f554ec6a/entities/GENE_PHENOTYPE_DATA_ENTITY"
        "/variables/VEUPATHDB_GENE_ID/distribution"
    )
    de = (
        "/studies/STUDY_e973eadd57/entities/ENT_fd574cd6"
        "/variables/VEUPATHDB_GENE_ID/distribution"
    )
    assert requests == {
        "gene_id_distribution_phenotype_filtered": (
            "plasmodb",
            phenotype,
            {"filters": [_SPECIES], "valueSpec": "count"},
        ),
        "gene_id_distribution_phenotype_unfiltered": (
            "plasmodb",
            phenotype,
            {"filters": [], "valueSpec": "count"},
        ),
        "gene_id_distribution_de_filtered": (
            "plasmodb",
            de,
            {"filters": [_SENSE_READS], "valueSpec": "count"},
        ),
        "gene_id_distribution_de_unfiltered": (
            "plasmodb",
            de,
            {"filters": [], "valueSpec": "count"},
        ),
    }


@pytest.mark.parametrize("capture", DISTRIBUTION_CAPTURES, ids=lambda c: c.name)
def test_every_request_body_is_the_one_the_pinned_raml_declares(
    capture: DistributionCapture,
) -> None:
    assert (
        verify_wire_body("VariableDistributionPostRequest", capture.request_body())
        == ()
    )


@pytest.mark.parametrize("capture", DISTRIBUTION_CAPTURES, ids=lambda c: c.name)
def test_every_recorded_body_is_bound_to_the_type_its_endpoint_returns(
    capture: DistributionCapture,
) -> None:
    bound = {b.fixture: b.raml_type for b in BINDINGS}

    assert bound[capture.name] == "VariableDistributionPostResponse"


async def test_a_capture_posts_the_request_and_keeps_the_first_bins() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        histogram = [_bin(f"PF3D7_010{n}") for n in range(5)]
        return httpx.Response(
            200, json={"histogram": histogram, "statistics": _STATISTICS}
        )

    client = EdaClient(base_url=_BASE, transport=httpx.MockTransport(handler))
    capture = _named("gene_id_distribution_de_filtered").model_copy(
        update={"kept_bins": 2}
    )

    body = await capture_distribution(capture, client=client)
    await client.close()

    assert [(r.method, r.url.path) for r in seen] == [("POST", f"/eda{capture.path}")]
    assert json.loads(seen[0].content) == capture.request_body()
    assert body == {
        "histogram": [_bin("PF3D7_0100"), _bin("PF3D7_0101")],
        "statistics": _STATISTICS,
    }


def test_a_write_keeps_the_body_and_states_the_trim(tmp_path: Path) -> None:
    (tmp_path / "provenance.json").write_text(
        (FIXTURE_DIR / "provenance.json").read_text()
    )
    capture = _named("gene_id_distribution_phenotype_unfiltered")
    body: JSONObject = {"histogram": [_bin("PBANKA_0100100")], "statistics": {}}

    write_distribution(
        capture, body, base_url=_BASE, recorded_at="2026-09-24", into=tmp_path
    )

    written = json.loads((tmp_path / f"{capture.name}.json").read_text())
    assert written == body
    assert load_provenance(tmp_path)[capture.name] == EdaFixtureProvenance(
        site="plasmodb",
        deployment=_BASE,
        method="POST",
        url=f"{_BASE}{capture.path}",
        status=200,
        content_type="application/json",
        body_shape="histogram,statistics",
        recorded_at="2026-09-24",
        trim=(
            f"the first {capture.kept_bins} histogram bins; the statistics are whole"
        ),
    )
    assert "analysis_detail_pass_and_de" in load_provenance(tmp_path)
