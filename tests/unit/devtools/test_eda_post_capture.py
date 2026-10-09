"""What ``eda_capture record`` asks a compute or a visualization, and what it writes."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.devtools.eda_capture import (
    POST_CAPTURES,
    CapturedPost,
    EdaFixtureProvenance,
    PostCapture,
    capture_post,
    load_provenance,
    write_post,
)
from veupathdb.devtools.eda_schemas import BINDINGS, verify_wire_body
from veupathdb.eda import EdaClient
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

_BASE = "https://qa.plasmodb.org/eda"
_JOB = "2679abb0e5c81b345a21b8f211db6a9b"
_REQUEST_TYPES = {
    "compute_job_dimensionalityreduction": "DimensionalityReductionPluginRequest",
    "computed_variables_dimensionalityreduction": (
        "DimensionalityReductionPluginRequest"
    ),
    "scatterplot_dimensionalityreduction": (
        "DimensionalityReductionScatterplotPostRequest"
    ),
    "conttable_genotype_by_temperature": "MosaicPostRequest",
    "boxplot_sense_reads_by_genotype": "BoxplotPostRequest",
    "scatterplot_best_fit_sense_antisense": "ScatterplotPostRequest",
}


@pytest.fixture(autouse=True)
def _service_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    yield
    veupathdb_auth_token_ctx.reset(token)


def _named(name: str) -> PostCapture:
    return next(c for c in POST_CAPTURES if c.name == name)


def test_the_captures_are_the_pca_run_and_three_pass_plots() -> None:
    assert {c.name: (c.path, c.awaits is not None) for c in POST_CAPTURES} == {
        "compute_job_dimensionalityreduction": (
            "/computes/dimensionalityreduction",
            True,
        ),
        "computed_variables_dimensionalityreduction": (
            "/computes/dimensionalityreduction/meta",
            True,
        ),
        "scatterplot_dimensionalityreduction": (
            "/apps/dimensionalityreduction/visualizations/scatterplot",
            True,
        ),
        "conttable_genotype_by_temperature": (
            "/apps/pass/visualizations/conttable",
            False,
        ),
        "boxplot_sense_reads_by_genotype": ("/apps/pass/visualizations/boxplot", False),
        "scatterplot_best_fit_sense_antisense": (
            "/apps/pass/visualizations/scatterplot",
            False,
        ),
    }


@pytest.mark.parametrize("capture", POST_CAPTURES, ids=lambda c: c.name)
def test_every_request_body_is_one_the_service_accepts(capture: PostCapture) -> None:
    assert verify_wire_body(_REQUEST_TYPES[capture.name], capture.body) == ()


@pytest.mark.parametrize("capture", POST_CAPTURES, ids=lambda c: c.name)
def test_every_recorded_body_is_bound_and_on_disk(capture: PostCapture) -> None:
    if needs_qa_recording(f"eda/{capture.name}.json"):
        pytest.skip(NEEDS_QA_RECORDING)
    bound = {b.fixture: b for b in BINDINGS}

    assert bound[capture.name].file == FIXTURE_DIR / f"{capture.name}.json"
    assert bound[capture.name].file.exists()


def test_the_pca_scatterplot_reads_the_job_the_compute_capture_starts() -> None:
    job = _named("compute_job_dimensionalityreduction")
    plot = _named("scatterplot_dimensionalityreduction")

    assert plot.awaits == job.awaits
    assert job.awaits is not None
    assert plot.body["computeConfig"] == job.body["config"]


async def test_a_capture_polls_its_job_to_complete_before_it_posts() -> None:
    seen: list[httpx.Request] = []
    statuses = iter(["queued", "in-progress", "complete"])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/meta"):
            return httpx.Response(
                200,
                content=b'{"variables":[]}',
                headers={"content-type": "text/plain; charset=UTF-8"},
            )
        return httpx.Response(200, json={"jobID": _JOB, "status": next(statuses)})

    client = EdaClient(base_url=_BASE, transport=httpx.MockTransport(handler))
    capture = _named("computed_variables_dimensionalityreduction")

    captured = await capture_post(capture, client=client, poll_seconds=0)
    await client.close()

    assert [(r.method, r.url.path) for r in seen] == [
        ("POST", "/eda/computes/dimensionalityreduction"),
        ("GET", f"/eda/jobs/{_JOB}"),
        ("GET", f"/eda/jobs/{_JOB}"),
        ("POST", "/eda/computes/dimensionalityreduction/meta"),
    ]
    assert seen[3].headers["accept"] == "text/plain"
    assert json.loads(seen[3].content) == capture.body
    assert captured == CapturedPost(content_type="text/plain", body={"variables": []})


async def test_a_failed_job_stops_the_capture() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"jobID": _JOB, "status": "failed"})

    client = EdaClient(base_url=_BASE, transport=httpx.MockTransport(handler))

    with pytest.raises(RuntimeError, match="ended failed"):
        await capture_post(
            _named("scatterplot_dimensionalityreduction"), client=client, poll_seconds=0
        )
    await client.close()

    assert [r.url.path for r in seen] == ["/eda/computes/dimensionalityreduction"]


@pytest.mark.skipif(
    needs_qa_recording("eda/provenance.json"), reason=NEEDS_QA_RECORDING
)
def test_a_write_names_the_query_and_the_content_type(tmp_path: Path) -> None:
    (tmp_path / "provenance.json").write_text(
        (FIXTURE_DIR / "provenance.json").read_text()
    )
    capture = _named("compute_job_dimensionalityreduction")
    captured = CapturedPost(
        content_type="application/json", body={"jobID": _JOB, "status": "complete"}
    )

    write_post(
        capture, captured, base_url=_BASE, recorded_at="2026-10-03", into=tmp_path
    )

    written = json.loads((tmp_path / f"{capture.name}.json").read_text())
    assert written == {"jobID": _JOB, "status": "complete"}
    assert load_provenance(tmp_path)[capture.name] == EdaFixtureProvenance(
        site="plasmodb",
        deployment=_BASE,
        method="POST",
        url=f"{_BASE}/computes/dimensionalityreduction?autostart=true",
        status=200,
        content_type="application/json",
        body_shape="jobID,status",
        recorded_at="2026-10-03",
    )


@pytest.mark.skipif(
    needs_qa_recording("eda/provenance.json"), reason=NEEDS_QA_RECORDING
)
def test_the_recorded_meta_body_came_as_text() -> None:
    entry = load_provenance(FIXTURE_DIR)["computed_variables_dimensionalityreduction"]

    assert entry.content_type == "text/plain"
    assert entry.url == f"{_BASE}/computes/dimensionalityreduction/meta"
