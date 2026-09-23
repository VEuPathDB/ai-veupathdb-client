"""An analysis descriptor holds every compute plugin the site offers."""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter

from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaComputeDescriptor,
    EdaDifferentialExpressionDescriptor,
    EdaOtherComputeDescriptor,
    EdaOtherVisualizationDescriptor,
    EdaPassDescriptor,
    EdaVisualizationDescriptor,
    EdaVolcanoDescriptor,
    differential_expression_computations,
)
from veupathdb.json_types import JSONObject
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

FIXTURE = "analysis_detail_pass_and_de.json"
COMPUTE = TypeAdapter(EdaComputeDescriptor)
VISUALIZATION = TypeAdapter(EdaVisualizationDescriptor)

_DE_CONFIGURATION: JSONObject = {
    "identifierVariable": {
        "entityId": "ENT_fd574cd6",
        "variableId": "VEUPATHDB_GENE_ID",
    },
    "valueVariable": {
        "entityId": "ENT_fd574cd6",
        "variableId": "SEQUENCE_READ_COUNT_ANTISENSE",
    },
    "comparator": {
        "variable": {"entityId": "ENT_8151325d", "variableId": "VAR_081ab087"},
        "groupA": [{"label": "normal"}],
        "groupB": [{"label": "febrile"}],
    },
}


def _recorded() -> JSONObject:
    return TypeAdapter(JSONObject).validate_json((FIXTURE_DIR / FIXTURE).read_text())


def _detail() -> EdaAnalysisDetail:
    return EdaAnalysisDetail.model_validate(_recorded())


def _computation(computation_id: str, descriptor: JSONObject) -> JSONObject:
    return {
        "computationId": computation_id,
        "descriptor": descriptor,
        "visualizations": [],
    }


def test_the_recorded_analysis_holds_a_pass_and_a_de_computation() -> None:
    detail = _detail()

    assert detail.num_computations == 2
    assert [c.computation_id for c in detail.descriptor.computations] == [
        "k3x9q",
        "m7p2d",
    ]


def test_the_pass_computation_is_the_pass_member() -> None:
    passed = _detail().descriptor.computations[0]

    assert passed.descriptor == EdaPassDescriptor()
    assert passed.display_name is None


def test_the_histogram_is_the_permissive_visualization_member() -> None:
    histogram = _detail().descriptor.computations[0].visualizations[0].descriptor

    assert isinstance(histogram, EdaOtherVisualizationDescriptor)
    assert histogram.type == "histogram"
    assert histogram.configuration == {
        "dependentAxisLogScale": False,
        "valueSpec": "count",
        "independentAxisValueSpec": "Full",
        "dependentAxisValueSpec": "Full",
        "xAxisVariable": {"entityId": "ENT_8151325d", "variableId": "VAR_7033e90f"},
    }
    assert histogram.thumbnail is not None
    assert histogram.thumbnail.startswith("data:image/png;base64,")


def test_the_de_computation_is_the_de_member() -> None:
    de = _detail().descriptor.computations[1]

    assert isinstance(de.descriptor, EdaDifferentialExpressionDescriptor)
    assert de.descriptor.configuration.value_variable.variable_id == (
        "SEQUENCE_READ_COUNT_ANTISENSE"
    )
    assert de.descriptor.configuration.differential_expression_method == "DESeq"
    assert de.display_name == "Unnamed computation"


def test_the_volcano_is_the_volcano_member_and_keeps_the_ui_settings() -> None:
    volcano = _detail().descriptor.computations[1].visualizations[0].descriptor

    assert isinstance(volcano, EdaVolcanoDescriptor)
    assert volcano.configuration.effect_size_threshold == 1.0
    assert volcano.configuration.significance_threshold == 0.05
    assert volcano.configuration.marker_body_opacity == 0.5


@pytest.mark.parametrize(
    ("raw", "configuration"),
    [
        (
            {"type": "alphadiv", "configuration": {"alphaDivMethod": "shannon"}},
            {"alphaDivMethod": "shannon"},
        ),
        ({"type": "example"}, None),
        ({"type": "futureplugin", "configuration": [1, "two"]}, [1, "two"]),
    ],
)
def test_an_unknown_compute_is_the_permissive_member(
    raw: JSONObject, configuration: object
) -> None:
    parsed = COMPUTE.validate_python(raw)

    assert isinstance(parsed, EdaOtherComputeDescriptor)
    assert parsed.type == raw["type"]
    assert parsed.configuration == configuration


def test_a_de_computation_the_ui_has_not_configured_is_the_permissive_member() -> None:
    """The UI stores every DE setting as optional until the researcher sets it."""
    raw: JSONObject = {
        "type": "differentialexpression",
        "configuration": {"differentialExpressionMethod": "DESeq"},
    }

    parsed = COMPUTE.validate_python(raw)

    assert isinstance(parsed, EdaOtherComputeDescriptor)
    assert parsed.configuration == {"differentialExpressionMethod": "DESeq"}


@pytest.mark.parametrize("kind", ["scatterplot", "boxplot", "barplot", "mapmarkers"])
def test_an_unknown_visualization_is_the_permissive_member(kind: str) -> None:
    raw: JSONObject = {
        "type": kind,
        "configuration": {"valueSpec": "raw"},
        "currentPlotFilters": [{"anything": "kept"}],
        "applicationContext": "pie",
    }

    parsed = VISUALIZATION.validate_python(raw)

    assert isinstance(parsed, EdaOtherVisualizationDescriptor)
    assert VISUALIZATION.dump_python(parsed, by_alias=True, exclude_none=True) == raw


def test_a_volcano_without_its_thresholds_is_the_permissive_member() -> None:
    raw: JSONObject = {"type": "volcanoplot", "configuration": {}}

    parsed = VISUALIZATION.validate_python(raw)

    assert isinstance(parsed, EdaOtherVisualizationDescriptor)
    assert parsed.type == "volcanoplot"


def test_the_helper_returns_the_de_computations_in_order() -> None:
    descriptor = EdaAnalysisDescriptor.model_validate(
        {
            "computations": [
                _computation(
                    "de1",
                    {
                        "type": "differentialexpression",
                        "configuration": _DE_CONFIGURATION,
                    },
                ),
                _computation("pass1", {"type": "pass"}),
                _computation("alpha1", {"type": "alphadiv", "configuration": {}}),
                _computation(
                    "de2",
                    {
                        "type": "differentialexpression",
                        "configuration": _DE_CONFIGURATION,
                    },
                ),
                _computation(
                    "draft",
                    {"type": "differentialexpression", "configuration": {}},
                ),
            ]
        }
    )

    found = differential_expression_computations(descriptor)

    assert [c.computation.computation_id for c in found] == ["de1", "de2"]
    assert [c.computation for c in found] == [
        descriptor.computations[0],
        descriptor.computations[3],
    ]
    assert [c.descriptor.configuration.comparator.group_b[0].label for c in found] == [
        "febrile",
        "febrile",
    ]


def test_the_helper_on_the_recorded_analysis_returns_the_one_de_computation() -> None:
    detail = _detail()

    found = differential_expression_computations(detail.descriptor)

    assert [c.computation.computation_id for c in found] == ["m7p2d"]
    assert found[0].descriptor is detail.descriptor.computations[1].descriptor


def test_a_read_descriptor_writes_back_every_key_the_site_stored() -> None:
    """A PATCH after a read keeps the computations PathFinder does not drive."""
    recorded = _recorded()

    written = json.loads(
        _detail().descriptor.model_dump_json(by_alias=True, exclude_unset=True)
    )

    assert written == recorded["descriptor"]


def test_a_read_detail_writes_back_every_modelled_wire_key() -> None:
    recorded = _recorded()

    written = json.loads(_detail().model_dump_json(by_alias=True, exclude_unset=True))

    assert set(written) <= set(recorded)
    assert written["descriptor"] == recorded["descriptor"]
