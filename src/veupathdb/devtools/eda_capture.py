"""The recorded EDA analysis documents and distributions, and the command that records them.

An analysis capture creates an analysis on a live site under a registered
account, writes the descriptor the site's own EDA app would write, reads the
stored document back, and deletes the analysis. A distribution capture posts
one declared request. A POST capture first drives the compute job it reads to
complete, then posts one declared request. The read body is the fixture.

Usage::

    python -m veupathdb.devtools.eda_capture list
    python -m veupathdb.devtools.eda_capture record [--only NAME ...]

An analysis needs WDK_TEST_TOKEN, or WDK_TEST_EMAIL/WDK_TEST_PASSWORD: the
analysis routes are keyed by a registered user. A distribution, a compute and a
visualization need VEUPATHDB_AUTH_TOKEN, the deployment's token.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.devtools.qa_sites import use_qa_sites
from veupathdb.domain import VEUPATHDB_GENE_ID
from veupathdb.eda.analyses import EdaAnalysesClient
from veupathdb.eda.client import (
    EdaClient,
    compute_body,
    distribution_body,
    visualization_body,
)
from veupathdb.eda.factory import get_eda_analyses_client, get_eda_client
from veupathdb.eda.models import (
    EdaBoxplotConfig,
    EdaComputeConfig,
    EdaDimensionalityReductionConfig,
    EdaFilter,
    EdaMosaicConfig,
    EdaNewAnalysis,
    EdaNumberRangeFilter,
    EdaScatterplotConfig,
    EdaStringSetFilter,
    EdaVariableSpec,
)
from veupathdb.json_types import JSONObject
from veupathdb.testing.eda_fixtures import FIXTURE_DIR
from veupathdb.testing.wdk_credentials import (
    NO_CREDENTIALS_REASON,
    registered_wdk_token,
)
from veupathdb.wdk.factory import get_site, get_wdk_client

PROVENANCE_FILE = "provenance.json"
_BODY: TypeAdapter[JSONObject] = TypeAdapter(JSONObject)


class EdaFixtureProvenance(BaseModel):
    """Where one recorded EDA body came from, and what was cut from it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    site: str
    deployment: str
    method: str
    url: str
    status: int
    content_type: str
    body_shape: str
    recorded_at: str
    trim: str = ""


_PROVENANCE: TypeAdapter[dict[str, EdaFixtureProvenance]] = TypeAdapter(
    dict[str, EdaFixtureProvenance]
)


class AnalysisCapture(BaseModel):
    """One analysis document to record, and the descriptor that makes it."""

    model_config = ConfigDict(frozen=True)

    name: str
    site: str
    dataset_id: str
    descriptor: JSONObject


class CapturedAnalysis(BaseModel):
    """The stored document a capture read back, and the id it had."""

    model_config = ConfigDict(frozen=True)

    analysis_id: str
    body: JSONObject


_HISTOGRAM_THUMBNAIL = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
    "2mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

# The shapes of web-monorepo eda/src/lib/core/types/visualization.ts and the
# defaults its HistogramVisualization and VolcanoPlotVisualization write.
_PASS_AND_DE_DESCRIPTOR: JSONObject = {
    "subset": {"descriptor": [], "uiSettings": {}},
    "computations": [
        {
            "computationId": "k3x9q",
            "descriptor": {"type": "pass"},
            "visualizations": [
                {
                    "visualizationId": "0b6f1c2e-5a3d-4e8f-9c71-2d4a6b8e0f13",
                    "displayName": "Unnamed visualization",
                    "descriptor": {
                        "type": "histogram",
                        "configuration": {
                            "dependentAxisLogScale": False,
                            "valueSpec": "count",
                            "independentAxisValueSpec": "Full",
                            "dependentAxisValueSpec": "Full",
                            "xAxisVariable": {
                                "entityId": "ENT_8151325d",
                                "variableId": "VAR_7033e90f",
                            },
                        },
                        "currentPlotFilters": [],
                        "thumbnail": _HISTOGRAM_THUMBNAIL,
                    },
                }
            ],
        },
        {
            "computationId": "m7p2d",
            "displayName": "Unnamed computation",
            "descriptor": {
                "type": "differentialexpression",
                "configuration": {
                    "identifierVariable": {
                        "entityId": "ENT_fd574cd6",
                        "variableId": "VEUPATHDB_GENE_ID",
                    },
                    "valueVariable": {
                        "entityId": "ENT_fd574cd6",
                        "variableId": "SEQUENCE_READ_COUNT_ANTISENSE",
                    },
                    "comparator": {
                        "variable": {
                            "entityId": "ENT_8151325d",
                            "variableId": "VAR_081ab087",
                        },
                        "groupA": [{"label": "normal"}],
                        "groupB": [{"label": "febrile"}],
                    },
                    "differentialExpressionMethod": "DESeq",
                    "pValueFloor": "1e-200",
                },
            },
            "visualizations": [
                {
                    "visualizationId": "7e2c4a91-3b5d-4f60-8a1e-9c0d2b4f6a85",
                    "displayName": "Unnamed visualization",
                    "descriptor": {
                        "type": "volcanoplot",
                        "configuration": {
                            "effectSizeThreshold": 1,
                            "significanceThreshold": 0.05,
                            "markerBodyOpacity": 0.5,
                            "effectDirection": "upAndDown",
                        },
                        "currentPlotFilters": [],
                    },
                }
            ],
        },
    ],
    "starredVariables": [],
    "dataTableConfig": {},
    "derivedVariables": [],
}

ANALYSIS_CAPTURES: tuple[AnalysisCapture, ...] = (
    AnalysisCapture(
        name="analysis_detail_pass_and_de",
        site="plasmodb",
        dataset_id="DS_e973eadd57",
        descriptor=_PASS_AND_DE_DESCRIPTOR,
    ),
)


class DistributionCapture(BaseModel):
    """One ``/distribution`` read to record, and the request that makes it."""

    model_config = ConfigDict(frozen=True)

    name: str
    site: str
    study_id: str
    entity_id: str
    variable_id: str
    filters: tuple[EdaFilter, ...] = ()
    kept_bins: int

    @property
    def path(self) -> str:
        return (
            f"/studies/{self.study_id}/entities/{self.entity_id}"
            f"/variables/{self.variable_id}/distribution"
        )

    def request_body(self) -> dict[str, JsonValue]:
        return distribution_body(self.filters)


class _DistributionBody(BaseModel):
    """The two members a ``VariableDistributionPostResponse`` closes itself to."""

    model_config = ConfigDict(extra="forbid")

    histogram: list[JSONObject]
    statistics: JSONObject


_PHENOTYPE_SPECIES = EdaStringSetFilter(
    entity_id="GENE_PHENOTYPE_DATA_ENTITY",
    variable_id="VAR_035294d0",
    string_set=["P. berghei"],
)
_DE_SENSE_READS = EdaNumberRangeFilter(
    entity_id="ENT_fd574cd6",
    variable_id="SEQUENCE_READ_COUNT_SENSE",
    min=1000,
    max=61892,
)
_GENE_ID_BINS_KEPT = 20


def _gene_ids(
    study: str, study_id: str, entity_id: str, subset: EdaFilter
) -> tuple[DistributionCapture, ...]:
    """The gene-id distribution of one gene entity, under ``subset`` and under none."""
    return tuple(
        DistributionCapture(
            name=f"gene_id_distribution_{study}_{label}",
            site="plasmodb",
            study_id=study_id,
            entity_id=entity_id,
            variable_id=VEUPATHDB_GENE_ID,
            filters=filters,
            kept_bins=_GENE_ID_BINS_KEPT,
        )
        for label, filters in (("filtered", (subset,)), ("unfiltered", ()))
    )


DISTRIBUTION_CAPTURES: tuple[DistributionCapture, ...] = (
    *_gene_ids(
        "phenotype",
        "STUDY_53f554ec6a",
        "GENE_PHENOTYPE_DATA_ENTITY",
        _PHENOTYPE_SPECIES,
    ),
    *_gene_ids("de", "STUDY_e973eadd57", "ENT_fd574cd6", _DE_SENSE_READS),
)


class ComputeRun(BaseModel):
    """A compute job a capture reads. The recorder drives it to complete first."""

    model_config = ConfigDict(frozen=True)

    compute_name: str
    study_id: str
    config: EdaComputeConfig


class PostCapture(BaseModel):
    """One POST to record whole, and the compute job it reads, if any."""

    model_config = ConfigDict(frozen=True)

    name: str
    site: str
    path: str
    body: JSONObject
    params: dict[str, str] = Field(default_factory=dict)
    accept: str = "application/json"
    awaits: ComputeRun | None = None

    @property
    def url_path(self) -> str:
        """The path with its query, as the provenance names it."""
        return f"{self.path}?{urlencode(self.params)}" if self.params else self.path


class CapturedPost(BaseModel):
    """The body a POST capture read, and the content type it was sent as."""

    model_config = ConfigDict(frozen=True)

    content_type: str
    body: JSONObject


_DE_STUDY = "STUDY_e973eadd57"
_SAMPLE = "ENT_8151325d"
_COUNTS = "ENT_fd574cd6"
_GENOTYPE = EdaVariableSpec(entity_id=_SAMPLE, variable_id="VAR_84f17484")
_TEMPERATURE_CONDITION = EdaVariableSpec(entity_id=_SAMPLE, variable_id="VAR_081ab087")
_SENSE_READS = EdaVariableSpec(
    entity_id=_COUNTS, variable_id="SEQUENCE_READ_COUNT_SENSE"
)
_ANTISENSE_READS = EdaVariableSpec(
    entity_id=_COUNTS, variable_id="SEQUENCE_READ_COUNT_ANTISENSE"
)
_SIX_GENES = EdaStringSetFilter(
    entity_id=_COUNTS,
    variable_id=VEUPATHDB_GENE_ID,
    string_set=[f"PF3D7_0100{n}00" for n in range(1, 7)],
)
_PCA = ComputeRun(
    compute_name="dimensionalityreduction",
    study_id=_DE_STUDY,
    config=EdaDimensionalityReductionConfig(
        identifier_variable=EdaVariableSpec(
            entity_id=_COUNTS, variable_id=VEUPATHDB_GENE_ID
        ),
        value_variable=_SENSE_READS,
        data_format="rawCounts",
    ),
)
_PCA_BODY = compute_body(_PCA.study_id, _PCA.config, [])


def _principal_component(number: int) -> EdaVariableSpec:
    return EdaVariableSpec(entity_id=_SAMPLE, variable_id=f"PC{number}")


POST_CAPTURES: tuple[PostCapture, ...] = (
    PostCapture(
        name="compute_job_dimensionalityreduction",
        site="plasmodb",
        path="/computes/dimensionalityreduction",
        body=_PCA_BODY,
        params={"autostart": "true"},
        awaits=_PCA,
    ),
    PostCapture(
        name="computed_variables_dimensionalityreduction",
        site="plasmodb",
        path="/computes/dimensionalityreduction/meta",
        body=_PCA_BODY,
        accept="text/plain",
        awaits=_PCA,
    ),
    PostCapture(
        name="scatterplot_dimensionalityreduction",
        site="plasmodb",
        path="/apps/dimensionalityreduction/visualizations/scatterplot",
        body=visualization_body(
            _DE_STUDY,
            [],
            EdaScatterplotConfig(
                output_entity_id=_SAMPLE,
                value_spec="raw",
                x_axis_variable=_principal_component(1),
                y_axis_variable=_principal_component(2),
                overlay_variable=_GENOTYPE,
            ),
            _PCA.config,
        ),
        awaits=_PCA,
    ),
    PostCapture(
        name="conttable_genotype_by_temperature",
        site="plasmodb",
        path="/apps/pass/visualizations/conttable",
        body=visualization_body(
            _DE_STUDY,
            [],
            EdaMosaicConfig(
                output_entity_id=_SAMPLE,
                x_axis_variable=_GENOTYPE,
                y_axis_variable=_TEMPERATURE_CONDITION,
            ),
        ),
    ),
    PostCapture(
        name="boxplot_sense_reads_by_genotype",
        site="plasmodb",
        path="/apps/pass/visualizations/boxplot",
        body=visualization_body(
            _DE_STUDY,
            [_SIX_GENES],
            EdaBoxplotConfig(
                output_entity_id=_COUNTS,
                x_axis_variable=_GENOTYPE,
                y_axis_variable=_SENSE_READS,
            ),
        ),
    ),
    PostCapture(
        name="scatterplot_best_fit_sense_antisense",
        site="plasmodb",
        path="/apps/pass/visualizations/scatterplot",
        body=visualization_body(
            _DE_STUDY,
            [_SIX_GENES],
            EdaScatterplotConfig(
                output_entity_id=_COUNTS,
                value_spec="bestFitLineWithRaw",
                x_axis_variable=_SENSE_READS,
                y_axis_variable=_ANTISENSE_READS,
                overlay_variable=_TEMPERATURE_CONDITION,
            ),
        ),
    ),
)

_JOB_POLLS = 60
_JOB_POLL_SECONDS = 5.0


async def complete_job(
    run: ComputeRun, *, client: EdaClient, poll_seconds: float = _JOB_POLL_SECONDS
) -> None:
    """Start the job and poll it until it completes. Any other end raises."""
    job = await client.submit_compute(
        compute_name=run.compute_name,
        study_id=run.study_id,
        config=run.config,
        filters=[],
    )
    for _ in range(_JOB_POLLS):
        if job.status == "complete":
            return
        if job.status not in {"queued", "in-progress"}:
            msg = f"{run.compute_name} job {job.job_id} ended {job.status}"
            raise RuntimeError(msg)
        await asyncio.sleep(poll_seconds)
        job = await client.get_job(job.job_id)
    msg = f"{run.compute_name} job {job.job_id} did not complete"
    raise TimeoutError(msg)


async def capture_post(
    capture: PostCapture, *, client: EdaClient, poll_seconds: float = _JOB_POLL_SECONDS
) -> CapturedPost:
    """Complete the job the capture reads, then post the declared request."""
    if capture.awaits is not None:
        await complete_job(capture.awaits, client=client, poll_seconds=poll_seconds)
    response = await client.send(
        "POST",
        capture.path,
        json=capture.body,
        params=capture.params,
        accept=capture.accept,
    )
    content_type, _, _ = response.headers["content-type"].partition(";")
    return CapturedPost(
        content_type=content_type, body=_BODY.validate_json(response.content)
    )


def load_provenance(directory: Path) -> dict[str, EdaFixtureProvenance]:
    """Every provenance entry the store in *directory* holds."""
    return _PROVENANCE.validate_json((directory / PROVENANCE_FILE).read_text())


async def capture_analysis(
    capture: AnalysisCapture,
    *,
    client: EdaClient,
    analyses: EdaAnalysesClient,
    user_id: str,
) -> CapturedAnalysis:
    """Create, write, read and delete one analysis. The delete runs on any failure."""
    created = await analyses.create(
        user_id=user_id,
        analysis=EdaNewAnalysis(
            study_id=capture.dataset_id,
            display_name=f"veupathdb-py fixture {capture.name}",
        ),
    )
    path = f"{analyses.collection_path(user_id)}/{created.analysis_id}"
    try:
        await client.request_json(
            "PATCH", path, json={"descriptor": capture.descriptor}
        )
        body = _BODY.validate_python(await client.request_json("GET", path))
    finally:
        await analyses.delete(user_id=user_id, analysis_id=created.analysis_id)
    return CapturedAnalysis(analysis_id=created.analysis_id, body=body)


async def capture_distribution(
    capture: DistributionCapture, *, client: EdaClient
) -> JSONObject:
    """Post the declared request and keep the first ``kept_bins`` bins."""
    raw = await client.request_json("POST", capture.path, json=capture.request_body())
    body = _DistributionBody.model_validate(raw)
    return {
        "histogram": list(body.histogram[: capture.kept_bins]),
        "statistics": body.statistics,
    }


def _write_fixture(
    name: str, body: JSONObject, provenance: EdaFixtureProvenance, *, into: Path
) -> None:
    (into / f"{name}.json").write_text(json.dumps(body, indent=2) + "\n")
    entries = load_provenance(into) | {name: provenance}
    ordered = dict(sorted(entries.items()))
    (into / PROVENANCE_FILE).write_text(
        _PROVENANCE.dump_json(ordered, indent=2).decode() + "\n"
    )


def write_capture(
    capture: AnalysisCapture,
    captured: CapturedAnalysis,
    *,
    base_url: str,
    project_id: str,
    recorded_at: str,
    into: Path,
) -> None:
    """Write the body and its provenance. The url names no account."""
    _write_fixture(
        capture.name,
        captured.body,
        EdaFixtureProvenance(
            site=capture.site,
            deployment=base_url,
            method="GET",
            url=(
                f"{base_url}/users/{{user-id}}/analyses/{project_id}/"
                f"{captured.analysis_id}"
            ),
            status=200,
            content_type="application/json",
            body_shape=",".join(sorted(captured.body)),
            recorded_at=recorded_at,
        ),
        into=into,
    )


def write_distribution(
    capture: DistributionCapture,
    body: JSONObject,
    *,
    base_url: str,
    recorded_at: str,
    into: Path,
) -> None:
    """Write the body and its provenance, which states the bins cut from it."""
    _write_fixture(
        capture.name,
        body,
        EdaFixtureProvenance(
            site=capture.site,
            deployment=base_url,
            method="POST",
            url=f"{base_url}{capture.path}",
            status=200,
            content_type="application/json",
            body_shape=",".join(sorted(body)),
            recorded_at=recorded_at,
            trim=(
                f"the first {capture.kept_bins} histogram bins; "
                "the statistics are whole"
            ),
        ),
        into=into,
    )


def write_post(
    capture: PostCapture,
    captured: CapturedPost,
    *,
    base_url: str,
    recorded_at: str,
    into: Path,
) -> None:
    """Write the whole body and its provenance, with the content type it came as."""
    _write_fixture(
        capture.name,
        captured.body,
        EdaFixtureProvenance(
            site=capture.site,
            deployment=base_url,
            method="POST",
            url=f"{base_url}{capture.url_path}",
            status=200,
            content_type=captured.content_type,
            body_shape=",".join(sorted(captured.body)),
            recorded_at=recorded_at,
        ),
        into=into,
    )


async def record_analyses(wanted: list[AnalysisCapture]) -> int:
    """Record each analysis capture on its QA site under the registered test account."""
    use_qa_sites()
    if not wanted:
        return 0
    token = await registered_wdk_token()
    if token is None:
        raise RuntimeError(NO_CREDENTIALS_REASON)
    veupathdb_auth_token_ctx.set(token)
    today = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    for capture in wanted:
        analyses = get_eda_analyses_client(capture.site)
        user_id = await analyses.resolve_user_id(get_wdk_client(capture.site))
        captured = await capture_analysis(
            capture,
            client=get_eda_client(capture.site),
            analyses=analyses,
            user_id=user_id,
        )
        write_capture(
            capture,
            captured,
            base_url=get_site(capture.site).eda_base_url.rstrip("/"),
            project_id=analyses.project_id,
            recorded_at=today,
            into=FIXTURE_DIR,
        )
        print(f"{capture.name}: analysis {captured.analysis_id} recorded and deleted")
    return len(wanted)


async def record_distributions(wanted: list[DistributionCapture]) -> int:
    """Record each distribution capture on its QA site under the deployment's token."""
    use_qa_sites()
    today = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    for capture in wanted:
        body = await capture_distribution(capture, client=get_eda_client(capture.site))
        write_distribution(
            capture,
            body,
            base_url=get_site(capture.site).eda_base_url.rstrip("/"),
            recorded_at=today,
            into=FIXTURE_DIR,
        )
        print(f"{capture.name}: {capture.path} recorded")
    return len(wanted)


async def record_posts(wanted: list[PostCapture]) -> int:
    """Record each POST capture on its QA site under the deployment's token."""
    use_qa_sites()
    today = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    for capture in wanted:
        captured = await capture_post(capture, client=get_eda_client(capture.site))
        write_post(
            capture,
            captured,
            base_url=get_site(capture.site).eda_base_url.rstrip("/"),
            recorded_at=today,
            into=FIXTURE_DIR,
        )
        print(f"{capture.name}: {capture.url_path} recorded")
    return len(wanted)


def _declared() -> list[tuple[str, str]]:
    """The name and the site of every capture of every kind."""
    return (
        [(c.name, c.site) for c in ANALYSIS_CAPTURES]
        + [(c.name, c.site) for c in DISTRIBUTION_CAPTURES]
        + [(c.name, c.site) for c in POST_CAPTURES]
    )


async def record(names: list[str]) -> int:
    """Record the named captures on the QA sites, or every capture when none are named."""
    use_qa_sites()
    unknown = sorted(set(names) - {name for name, _site in _declared()})
    if unknown:
        msg = f"no capture is named {', '.join(unknown)}"
        raise KeyError(msg)
    analyses = [c for c in ANALYSIS_CAPTURES if not names or c.name in names]
    distributions = [c for c in DISTRIBUTION_CAPTURES if not names or c.name in names]
    posts = [c for c in POST_CAPTURES if not names or c.name in names]
    return (
        await record_analyses(analyses)
        + await record_distributions(distributions)
        + await record_posts(posts)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eda_capture", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show the captures and what is on disk")
    recorder = sub.add_parser("record", help="record the captures live")
    recorder.add_argument("--only", nargs="*", default=[], metavar="NAME")
    args = parser.parse_args(argv)

    if args.command == "list":
        for name, site in _declared():
            state = "recorded" if (FIXTURE_DIR / f"{name}.json").exists() else "MISSING"
            print(f"{name:42} {state:9} {site}")
        return 0
    count = asyncio.run(record(args.only))
    print(f"recorded {count} fixture(s) into {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "ANALYSIS_CAPTURES",
    "DISTRIBUTION_CAPTURES",
    "POST_CAPTURES",
    "PROVENANCE_FILE",
    "AnalysisCapture",
    "CapturedAnalysis",
    "CapturedPost",
    "ComputeRun",
    "DistributionCapture",
    "EdaFixtureProvenance",
    "PostCapture",
    "capture_analysis",
    "capture_distribution",
    "capture_post",
    "complete_job",
    "load_provenance",
    "main",
    "record",
    "record_analyses",
    "record_distributions",
    "record_posts",
    "write_capture",
    "write_distribution",
    "write_post",
]
