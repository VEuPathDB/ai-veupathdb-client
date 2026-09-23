"""What ``eda_capture record`` asks the analysis store, and what it writes."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.devtools.eda_capture import (
    ANALYSIS_CAPTURES,
    AnalysisCapture,
    CapturedAnalysis,
    EdaFixtureProvenance,
    capture_analysis,
    load_provenance,
    write_capture,
)
from veupathdb.eda import EdaAnalysesClient, EdaAnalysisDescriptor, EdaClient
from veupathdb.eda.errors import EdaServerError
from veupathdb.json_types import JSONObject
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

_BASE = "https://plasmodb.org/eda"
_USER = "1234"
_ROOT = f"/eda/users/{_USER}/analyses/PlasmoDB"
_STORED: JSONObject = {
    "analysisId": "abc1234",
    "numComputations": 2,
    "descriptor": {"computations": []},
}


@pytest.fixture(autouse=True)
def _registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    yield
    veupathdb_auth_token_ctx.reset(token)


def _capture() -> AnalysisCapture:
    return ANALYSIS_CAPTURES[0]


def _stores(
    seen: list[httpx.Request], *, read_status: int = 200
) -> tuple[EdaClient, EdaAnalysesClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"analysisId": "abc1234"})
        if request.method == "GET":
            return httpx.Response(read_status, json=_STORED)
        return httpx.Response(204)

    client = EdaClient(base_url=_BASE, transport=httpx.MockTransport(handler))
    return client, EdaAnalysesClient(client=client, project_id="PlasmoDB")


def test_the_capture_holds_a_pass_and_a_de_computation() -> None:
    written = EdaAnalysisDescriptor.model_validate(_capture().descriptor)
    kinds = [computation.descriptor.type for computation in written.computations]

    assert _capture().name == "analysis_detail_pass_and_de"
    assert kinds == ["pass", "differentialexpression"]


async def test_a_capture_creates_patches_reads_and_deletes_in_that_order() -> None:
    seen: list[httpx.Request] = []
    client, analyses = _stores(seen)

    captured = await capture_analysis(
        _capture(), client=client, analyses=analyses, user_id=_USER
    )
    await client.close()

    assert [(r.method, r.url.path) for r in seen] == [
        ("POST", _ROOT),
        ("PATCH", f"{_ROOT}/abc1234"),
        ("GET", f"{_ROOT}/abc1234"),
        ("DELETE", f"{_ROOT}/abc1234"),
    ]
    assert json.loads(seen[0].content)["studyId"] == "DS_e973eadd57"
    assert json.loads(seen[1].content) == {"descriptor": _capture().descriptor}
    assert captured.analysis_id == "abc1234"
    assert captured.body == _STORED


async def test_a_failed_read_still_deletes_the_analysis() -> None:
    seen: list[httpx.Request] = []
    client, analyses = _stores(seen, read_status=500)

    with pytest.raises(EdaServerError):
        await capture_analysis(
            _capture(), client=client, analyses=analyses, user_id=_USER
        )
    await client.close()

    assert [r.method for r in seen] == ["POST", "PATCH", "GET", "DELETE"]


def test_a_write_keeps_the_body_and_names_no_account(tmp_path: Path) -> None:
    (tmp_path / "provenance.json").write_text(
        (FIXTURE_DIR / "provenance.json").read_text()
    )
    captured = CapturedAnalysis(analysis_id="abc1234", body=_STORED)

    write_capture(
        _capture(),
        captured,
        base_url=_BASE,
        project_id="PlasmoDB",
        recorded_at="2026-09-23",
        into=tmp_path,
    )

    written = json.loads((tmp_path / "analysis_detail_pass_and_de.json").read_text())
    entry = load_provenance(tmp_path)["analysis_detail_pass_and_de"]
    assert written == _STORED
    assert entry == EdaFixtureProvenance(
        site="plasmodb",
        deployment=_BASE,
        method="GET",
        url=f"{_BASE}/users/{{user-id}}/analyses/PlasmoDB/abc1234",
        status=200,
        content_type="application/json",
        body_shape="analysisId,descriptor,numComputations",
        recorded_at="2026-09-23",
        trim="",
    )
    assert load_provenance(tmp_path)["study_detail_de"].url == (
        f"{_BASE}/studies/STUDY_e973eadd57"
    )


def test_the_store_provenance_reads_back_unchanged() -> None:
    """Every entry on disk survives a read and a write through the model."""
    on_disk = json.loads((FIXTURE_DIR / "provenance.json").read_text())

    parsed = load_provenance(FIXTURE_DIR)

    assert {name: entry.model_dump() for name, entry in parsed.items()} == on_disk
