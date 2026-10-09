"""The PCA compute and the statistical visualizations over the recorded EDA wire."""

from __future__ import annotations

import json

import httpx
import pytest
from tests.unit.eda._hermetic import (
    eda_client,
    fixture,
    pca_config,
    registered_token,
    species_filter,
)

from veupathdb.eda.errors import EdaBadRequestError
from veupathdb.eda.models import (
    EdaBoxplotConfig,
    EdaMosaicConfig,
    EdaScatterplotConfig,
    EdaTwoByTwoConfig,
    EdaVariableSpec,
)
from veupathdb.testing import NEEDS_QA_RECORDING

pytestmark = pytest.mark.asyncio

__all__ = ["registered_token"]

_SAMPLE = "ENT_8151325d"
_COUNTS = "ENT_fd574cd6"
_GENOTYPE = EdaVariableSpec(entity_id=_SAMPLE, variable_id="VAR_84f17484")
_CONDITION = EdaVariableSpec(entity_id=_SAMPLE, variable_id="VAR_081ab087")
_SENSE = EdaVariableSpec(entity_id=_COUNTS, variable_id="SEQUENCE_READ_COUNT_SENSE")
_ANTISENSE = EdaVariableSpec(
    entity_id=_COUNTS, variable_id="SEQUENCE_READ_COUNT_ANTISENSE"
)
_PCA_CONFIG = {
    "identifierVariable": {"entityId": _COUNTS, "variableId": "VEUPATHDB_GENE_ID"},
    "valueVariable": {"entityId": _COUNTS, "variableId": "SEQUENCE_READ_COUNT_SENSE"},
    "dataFormat": "rawCounts",
}


def _pca_axes() -> EdaScatterplotConfig:
    return EdaScatterplotConfig(
        output_entity_id=_SAMPLE,
        value_spec="raw",
        x_axis_variable=EdaVariableSpec(entity_id=_SAMPLE, variable_id="PC1"),
        y_axis_variable=EdaVariableSpec(entity_id=_SAMPLE, variable_id="PC2"),
        overlay_variable=_GENOTYPE,
    )


def _answering(
    seen: list[httpx.Request], body: object, *, content_type: str = "application/json"
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, content=json.dumps(body), headers={"content-type": content_type}
        )

    return httpx.MockTransport(handler)


@pytest.mark.skip(reason=NEEDS_QA_RECORDING)
async def test_a_pca_submit_carries_the_pca_configuration() -> None:
    seen: list[httpx.Request] = []
    client = eda_client(
        _answering(seen, fixture("compute_job_dimensionalityreduction.json"))
    )

    job = await client.submit_compute(
        compute_name="dimensionalityreduction",
        study_id="STUDY_e973eadd57",
        config=pca_config(),
        filters=[],
    )
    await client.close()

    assert seen[0].url.path == "/eda/computes/dimensionalityreduction"
    assert seen[0].url.params["autostart"] == "true"
    assert json.loads(seen[0].content) == {
        "studyId": "STUDY_e973eadd57",
        "filters": [],
        "derivedVariables": [],
        "config": _PCA_CONFIG,
    }
    assert job.job_id == "2679abb0e5c81b345a21b8f211db6a9b"
    assert job.status == "complete"


@pytest.mark.skip(reason=NEEDS_QA_RECORDING)
async def test_the_meta_read_asks_for_text_and_parses_the_json_it_carries() -> None:
    """The meta route answers ``text/plain`` and refuses an ``application/json`` accept."""
    seen: list[httpx.Request] = []
    recorded = fixture("computed_variables_dimensionalityreduction.json")
    client = eda_client(_answering(seen, recorded, content_type="text/plain"))

    meta = await client.compute_meta(
        compute_name="dimensionalityreduction",
        study_id="STUDY_e973eadd57",
        config=pca_config(),
        filters=[species_filter()],
    )
    await client.close()

    assert seen[0].method == "POST"
    assert seen[0].url.path == "/eda/computes/dimensionalityreduction/meta"
    assert seen[0].headers["accept"] == "text/plain"
    assert "Authorization=token-hermetic" in seen[0].headers["cookie"]
    body = json.loads(seen[0].content)
    assert sorted(body) == ["config", "derivedVariables", "filters", "studyId"]
    assert body["config"] == _PCA_CONFIG
    assert [(v.variable_spec.variable_id, v.display_name) for v in meta.variables] == [
        ("PC1", "PC 1 (54.35% variance)"),
        ("PC2", "PC 2 (12.79% variance)"),
    ]
    assert {v.variable_spec.entity_id for v in meta.variables} == {_SAMPLE}
    assert [v.plot_reference for v in meta.variables] == ["xAxis", "yAxis"]
    assert meta.variables[0].variable_class == "computed"
    assert meta.variables[0].display_range_min == "-61.4351512946123"


@pytest.mark.skip(reason=NEEDS_QA_RECORDING)
async def test_the_pca_scatterplot_sends_the_compute_beside_the_plot() -> None:
    seen: list[httpx.Request] = []
    client = eda_client(
        _answering(seen, fixture("scatterplot_dimensionalityreduction.json"))
    )

    plot = await client.scatterplot(
        app="dimensionalityreduction",
        study_id="STUDY_e973eadd57",
        filters=[],
        config=_pca_axes(),
        compute_config=pca_config(),
    )
    await client.close()

    assert seen[0].url.path == (
        "/eda/apps/dimensionalityreduction/visualizations/scatterplot"
    )
    assert json.loads(seen[0].content) == {
        "studyId": "STUDY_e973eadd57",
        "filters": [],
        "config": {
            "outputEntityId": _SAMPLE,
            "valueSpec": "raw",
            "xAxisVariable": {"entityId": _SAMPLE, "variableId": "PC1"},
            "yAxisVariable": {"entityId": _SAMPLE, "variableId": "PC2"},
            "overlayVariable": {"entityId": _SAMPLE, "variableId": "VAR_84f17484"},
            "returnPointIds": True,
        },
        "computeConfig": _PCA_CONFIG,
    }
    assert [
        s.overlay_variable_details.value
        for s in plot.data
        if s.overlay_variable_details
    ] == [
        "delta-DHC mutant",
        "delta-LRR5 mutant",
        "wildtype",
    ]
    assert [len(s.series_x) for s in plot.data] == [4, 4, 4]
    wildtype = plot.data[2]
    assert wildtype.point_ids[0] == "WT_37C_Rep1"
    assert (wildtype.series_x[0], wildtype.series_y[0]) == (
        "-7.2548330125957",
        "-19.2972293300329",
    )
    axes = {v.plot_reference: v.display_name for v in plot.config.variables}
    assert axes["xAxis"] == "PC 1 (54.35% variance)"
    assert axes["yAxis"] == "PC 2 (12.79% variance)"
    assert plot.config.complete_cases_all_vars == 12
    assert [row.size for row in plot.sample_size_table] == [[4], [4], [4]]


@pytest.mark.skip(reason=NEEDS_QA_RECORDING)
async def test_a_pass_scatterplot_sends_no_compute_and_reads_the_best_fit() -> None:
    seen: list[httpx.Request] = []
    client = eda_client(
        _answering(seen, fixture("scatterplot_best_fit_sense_antisense.json"))
    )

    plot = await client.scatterplot(
        app="pass",
        study_id="STUDY_e973eadd57",
        filters=[],
        config=EdaScatterplotConfig(
            output_entity_id=_COUNTS,
            value_spec="bestFitLineWithRaw",
            x_axis_variable=_SENSE,
            y_axis_variable=_ANTISENSE,
            overlay_variable=_CONDITION,
        ),
    )
    await client.close()

    assert seen[0].url.path == "/eda/apps/pass/visualizations/scatterplot"
    assert sorted(json.loads(seen[0].content)) == ["config", "filters", "studyId"]
    febrile, normal = plot.data
    assert (febrile.r2, normal.r2) == (0.106, 0.3168)
    assert (len(febrile.series_x), len(normal.series_x)) == (36, 36)
    assert (len(febrile.best_fit_line_x), len(normal.best_fit_line_x)) == (20, 14)
    assert (febrile.best_fit_line_x[-1], febrile.best_fit_line_y[-1]) == (
        "437",
        15.4285,
    )
    assert febrile.point_ids[0] == "PB31_41C_Rep1.PF3D7_0100100"


@pytest.mark.skip(reason=NEEDS_QA_RECORDING)
async def test_a_contingency_table_reads_the_counts_and_the_chi_squared_test() -> None:
    seen: list[httpx.Request] = []
    client = eda_client(
        _answering(seen, fixture("conttable_genotype_by_temperature.json"))
    )

    table = await client.contingency_table(
        study_id="STUDY_e973eadd57",
        filters=[],
        config=EdaMosaicConfig(
            output_entity_id=_SAMPLE,
            x_axis_variable=_GENOTYPE,
            y_axis_variable=_CONDITION,
        ),
    )
    await client.close()

    assert seen[0].url.path == "/eda/apps/pass/visualizations/conttable"
    assert json.loads(seen[0].content) == {
        "studyId": "STUDY_e973eadd57",
        "filters": [],
        "config": {
            "outputEntityId": _SAMPLE,
            "xAxisVariable": {"entityId": _SAMPLE, "variableId": "VAR_84f17484"},
            "yAxisVariable": {"entityId": _SAMPLE, "variableId": "VAR_081ab087"},
        },
    }
    assert table.counts.x_label == ["delta-DHC mutant", "delta-LRR5 mutant", "wildtype"]
    assert table.counts.y_label[0] == ["febrile", "normal"]
    assert table.counts.value == [[2, 2], [2, 2], [2, 2]]
    assert (table.chisq, table.pvalue, table.degrees_freedom) == (0.0, 1.0, 2.0)
    axis = table.sample_size_table[0].x_variable_details
    assert axis is not None
    assert axis.value == ["delta-DHC mutant", "delta-LRR5 mutant", "wildtype"]
    assert table.sample_size_table[0].size == [4, 4, 4]


@pytest.mark.skip(reason=NEEDS_QA_RECORDING)
async def test_a_boxplot_reads_one_group_per_label() -> None:
    seen: list[httpx.Request] = []
    client = eda_client(
        _answering(seen, fixture("boxplot_sense_reads_by_genotype.json"))
    )

    plot = await client.boxplot(
        study_id="STUDY_e973eadd57",
        filters=[],
        config=EdaBoxplotConfig(
            output_entity_id=_COUNTS,
            x_axis_variable=_GENOTYPE,
            y_axis_variable=_SENSE,
        ),
    )
    await client.close()

    assert seen[0].url.path == "/eda/apps/pass/visualizations/boxplot"
    assert json.loads(seen[0].content)["config"] == {
        "outputEntityId": _COUNTS,
        "points": "outliers",
        "mean": "TRUE",
        "xAxisVariable": {"entityId": _SAMPLE, "variableId": "VAR_84f17484"},
        "yAxisVariable": {
            "entityId": _COUNTS,
            "variableId": "SEQUENCE_READ_COUNT_SENSE",
        },
    }
    groups = plot.data[0].groups
    assert [g.label for g in groups] == [
        "delta-DHC mutant",
        "delta-LRR5 mutant",
        "wildtype",
    ]
    wildtype = groups[2]
    assert (wildtype.q1, wildtype.median, wildtype.q3) == (1.0, 13.5, 45.5)
    assert (wildtype.lowerfence, wildtype.upperfence) == (0.0, 49.0)
    assert (wildtype.min, wildtype.max, wildtype.mean) == (0.0, 525.0, 76.7083)
    assert wildtype.outliers == [472.0, 525.0, 205.0, 328.0]
    assert plot.sample_size_table[0].size == [24, 24, 24]


@pytest.mark.skip(reason=NEEDS_QA_RECORDING)
async def test_a_compute_backed_boxplot_carries_the_compute() -> None:
    seen: list[httpx.Request] = []
    client = eda_client(
        _answering(seen, fixture("boxplot_sense_reads_by_genotype.json"))
    )

    await client.boxplot(
        study_id="STUDY_e973eadd57",
        filters=[],
        config=EdaBoxplotConfig(
            output_entity_id=_SAMPLE,
            x_axis_variable=_GENOTYPE,
            y_axis_variable=EdaVariableSpec(entity_id=_SAMPLE, variable_id="PC1"),
        ),
        app="dimensionalityreduction",
        compute_config=pca_config(),
    )
    await client.close()

    assert (
        seen[0].url.path == "/eda/apps/dimensionalityreduction/visualizations/boxplot"
    )
    assert json.loads(seen[0].content)["computeConfig"] == _PCA_CONFIG


async def test_a_two_by_two_sends_both_reference_values() -> None:
    seen: list[httpx.Request] = []
    client = eda_client(_answering(seen, _TWO_BY_TWO))

    table = await client.two_by_two(
        study_id="STUDY_e973eadd57",
        filters=[],
        config=EdaTwoByTwoConfig(
            output_entity_id=_SAMPLE,
            x_axis_variable=_CONDITION,
            y_axis_variable=_GENOTYPE,
            x_axis_reference_value="febrile",
            y_axis_reference_value="wildtype",
        ),
    )
    await client.close()

    assert seen[0].url.path == "/eda/apps/pass/visualizations/twobytwo"
    config = json.loads(seen[0].content)["config"]
    assert (config["xAxisReferenceValue"], config["yAxisReferenceValue"]) == (
        "febrile",
        "wildtype",
    )
    assert table.counts.value == [[3, 1], [1, 3]]
    assert table.odds_ratio is not None
    assert (table.odds_ratio.value, table.odds_ratio.pvalue) == (9.0, "0.4857")
    assert table.odds_ratio.confidence_interval == "0.3 - 271.9"
    assert table.fisher is not None
    assert table.fisher.pvalue == "0.4857"
    assert table.prevalence is None


async def test_a_two_by_two_the_service_cannot_evaluate_is_a_bad_request() -> None:
    client = eda_client(
        httpx.MockTransport(
            lambda _r: httpx.Response(
                400,
                json={
                    "status": "bad-request",
                    "message": "eval failed, request status: error code: 127",
                },
            )
        )
    )
    with pytest.raises(EdaBadRequestError):
        await client.two_by_two(
            study_id="STUDY_e973eadd57",
            filters=[],
            config=EdaTwoByTwoConfig(
                output_entity_id=_SAMPLE,
                x_axis_variable=_CONDITION,
                y_axis_variable=_GENOTYPE,
                x_axis_reference_value="febrile",
                y_axis_reference_value="wildtype",
            ),
        )
    await client.close()


def _statistic(value: float, pvalue: str, interval: str) -> dict[str, object]:
    return {
        "value": value,
        "pvalue": pvalue,
        "confidenceInterval": interval,
        "confidenceLevel": 0.95,
    }


# The statistic names the service's R package writes for a 2x2 table.
_TWO_BY_TWO = {
    "mosaic": {
        "data": [
            {
                "xLabel": ["febrile", "normal"],
                "yLabel": [["wildtype", "delta-DHC mutant"]] * 2,
                "value": [[3, 1], [1, 3]],
            }
        ],
        "config": {"variables": [], "completeCasesAllVars": 8},
    },
    "statsTable": [
        {
            "chiSq": _statistic(0.5, "0.4795", "NA"),
            "fisher": _statistic(9.0, "0.4857", "0.3 - 271.9"),
            "oddsRatio": _statistic(9.0, "0.4857", "0.3 - 271.9"),
            "relativeRisk": _statistic(3.0, "0.4857", "0.5 - 18.1"),
        }
    ],
    "sampleSizeTable": [],
    "completeCasesTable": [],
}
