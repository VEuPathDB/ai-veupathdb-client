"""A stored analysis read and written back carries exactly the keys the site stored."""

from __future__ import annotations

import copy
import json

import httpx
import pytest
from pydantic import TypeAdapter
from tests.unit.eda._hermetic import de_config, eda_client, registered_token

from veupathdb.eda import (
    EdaAnalysesClient,
    EdaAnalysisDescriptor,
    EdaComputation,
    EdaDifferentialExpressionDescriptor,
    EdaVisualization,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
    analysis_descriptor_patch,
)
from veupathdb.json_types import JSONObject
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

__all__ = ["registered_token"]

_COMPUTATIONS = TypeAdapter(list[JSONObject])

_STORED: JSONObject = {
    "subset": {"descriptor": [], "uiSettings": {"panel": "open"}},
    "computations": [
        {
            "computationId": "k3x9q",
            "descriptor": {"type": "pass", "configuration": {"legacy": True}},
            "visualizations": [
                {
                    "visualizationId": "h1",
                    "descriptor": {
                        "type": "histogram",
                        "configuration": {"valueSpec": "count", "showLegend": True},
                    },
                }
            ],
        },
        {
            "computationId": "m7p2d",
            "displayName": "heat shock",
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
                    "futureSetting": "kept",
                },
                "runNote": "kept",
            },
            "visualizations": [
                {
                    "visualizationId": "v1",
                    "descriptor": {
                        "type": "volcanoplot",
                        "configuration": {
                            "effectSizeThreshold": 1.0,
                            "significanceThreshold": 0.05,
                            "showLegend": True,
                        },
                        "pinnedPoints": ["PF3D7_0100100"],
                    },
                }
            ],
        },
    ],
    "starredVariables": [],
    "dataTableConfig": {},
    "derivedVariables": [],
}


def _read() -> EdaAnalysisDescriptor:
    return EdaAnalysisDescriptor.model_validate(copy.deepcopy(_STORED))


def _built_volcano() -> EdaVisualization:
    return EdaVisualization(
        visualization_id="v2",
        descriptor=EdaVolcanoDescriptor(
            configuration=EdaVolcanoConfiguration(
                effect_size_threshold=2.0, significance_threshold=0.01
            )
        ),
    )


_BUILT_VOLCANO_WIRE: JSONObject = {
    "visualizationId": "v2",
    "descriptor": {
        "type": "volcanoplot",
        "configuration": {
            "effectSizeThreshold": 2.0,
            "significanceThreshold": 0.01,
            "effectDirection": "upAndDown",
        },
        "currentPlotFilters": [],
    },
}


def test_a_read_descriptor_dumps_unset_excluded_as_the_site_stored_it() -> None:
    """Unknown keys stay, and no default the site did not store is added."""
    written = _read().model_dump(by_alias=True, exclude_unset=True)

    assert written == _STORED


def test_the_patch_body_of_a_read_descriptor_is_the_stored_one() -> None:
    assert analysis_descriptor_patch(_read()) == _STORED


def test_the_patch_body_of_the_recorded_analysis_is_the_stored_one() -> None:
    recorded = TypeAdapter(JSONObject).validate_json(
        (FIXTURE_DIR / "analysis_detail_pass_and_de.json").read_text()
    )
    descriptor = EdaAnalysisDescriptor.model_validate(recorded["descriptor"])

    assert analysis_descriptor_patch(descriptor) == recorded["descriptor"]


def test_a_built_computation_is_written_with_its_defaults() -> None:
    read = _read()
    built = EdaComputation(
        computation_id="de9",
        descriptor=EdaDifferentialExpressionDescriptor(configuration=de_config()),
        visualizations=[_built_volcano()],
    )

    body = analysis_descriptor_patch(
        read.model_copy(update={"computations": [*read.computations, built]})
    )

    computations = body["computations"]
    assert isinstance(computations, list)
    assert computations[:2] == _STORED["computations"]
    assert computations[2] == {
        "computationId": "de9",
        "descriptor": {
            "type": "differentialexpression",
            "configuration": {
                "identifierVariable": {
                    "entityId": "ENT_fd574cd6",
                    "variableId": "VEUPATHDB_GENE_ID",
                },
                "valueVariable": {
                    "entityId": "ENT_fd574cd6",
                    "variableId": "SEQUENCE_READ_COUNT_SENSE",
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
        "visualizations": [_BUILT_VOLCANO_WIRE],
    }


def test_a_built_visualization_on_a_read_computation_carries_its_defaults() -> None:
    read = _read()
    de = read.computations[1]
    replaced = de.model_copy(update={"visualizations": [_built_volcano()]})

    body = analysis_descriptor_patch(
        read.model_copy(update={"computations": [read.computations[0], replaced]})
    )

    stored = _COMPUTATIONS.validate_python(_STORED["computations"])
    assert body["computations"] == [
        stored[0],
        {**stored[1], "visualizations": [_BUILT_VOLCANO_WIRE]},
    ]


@pytest.mark.asyncio
async def test_patch_descriptor_sends_the_patch_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    client = eda_client(httpx.MockTransport(handler))
    analyses = EdaAnalysesClient(client=client, project_id="PlasmoDB")
    await analyses.patch_descriptor(
        user_id="1", analysis_id="t4fszEJ", descriptor=_read()
    )
    await client.close()

    assert json.loads(seen[0].content) == {"descriptor": _STORED}
