"""The plot models refuse a body whose parallel arrays do not line up."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from veupathdb.eda.models import (
    EdaBoxplotResponse,
    EdaBoxplotSeries,
    EdaComputeConfig,
    EdaContTableResponse,
    EdaDifferentialExpressionConfig,
    EdaDimensionalityReductionConfig,
    EdaMosaicCounts,
    EdaScatterplotSeries,
)
from veupathdb.json_types import JSONObject

COMPUTE_CONFIG = TypeAdapter(EdaComputeConfig)
_SPEC = {"entityId": "ENT_fd574cd6", "variableId": "VEUPATHDB_GENE_ID"}
_CONFIG: JSONObject = {"variables": []}


def test_a_scatterplot_series_with_unequal_axes_is_refused() -> None:
    with pytest.raises(ValidationError, match="one value per point"):
        EdaScatterplotSeries.model_validate({"seriesX": ["1", "2"], "seriesY": ["1"]})


def test_a_scatterplot_series_with_too_few_point_ids_is_refused() -> None:
    with pytest.raises(ValidationError, match="one id per point"):
        EdaScatterplotSeries.model_validate(
            {"seriesX": ["1", "2"], "seriesY": ["1", "2"], "pointIds": ["a"]}
        )


def test_a_best_fit_line_with_unequal_axes_is_refused() -> None:
    with pytest.raises(ValidationError, match="bestFitLineX"):
        EdaScatterplotSeries.model_validate(
            {"bestFitLineX": ["0", "1"], "bestFitLineY": [0.5]}
        )


def test_a_smoothed_mean_with_unequal_arrays_is_refused() -> None:
    with pytest.raises(ValidationError, match="smoothed mean"):
        EdaScatterplotSeries.model_validate(
            {
                "smoothedMeanX": ["0", "1"],
                "smoothedMeanY": [0.5, 0.6],
                "smoothedMeanSE": [0.1],
            }
        )


def test_a_smoothed_mean_series_carries_no_raw_points() -> None:
    series = EdaScatterplotSeries.model_validate(
        {
            "smoothedMeanX": ["0", "1"],
            "smoothedMeanY": [0.5, 0.6],
            "smoothedMeanSE": [0.1, 0.2],
        }
    )

    assert series.series_x == []
    assert list(zip(series.smoothed_mean_x, series.smoothed_mean_y, strict=True)) == [
        ("0", 0.5),
        ("1", 0.6),
    ]


def test_a_boxplot_column_shorter_than_its_labels_is_refused() -> None:
    with pytest.raises(ValidationError, match="one value per label"):
        EdaBoxplotSeries.model_validate(
            {
                "label": ["a", "b"],
                "lowerfence": [0, 0],
                "upperfence": [1, 1],
                "q1": [0, 0],
                "q3": [1],
                "median": [0.5, 0.5],
            }
        )


def test_a_boxplot_series_keeps_each_label_with_its_own_numbers() -> None:
    series = EdaBoxplotSeries.model_validate(
        {
            "overlayVariableDetails": {**_SPEC, "value": "febrile"},
            "label": ["a", "b"],
            "lowerfence": [0, 1],
            "upperfence": [4, 5],
            "q1": [1, 2],
            "q3": [3, 4],
            "median": [2, 3],
            "outliers": [[], [9, 10]],
        }
    )

    assert series.overlay_variable_details is not None
    assert series.overlay_variable_details.value == "febrile"
    assert [(g.label, g.median, g.outliers) for g in series.groups] == [
        ("a", 2.0, []),
        ("b", 3.0, [9.0, 10.0]),
    ]
    assert [g.mean for g in series.groups] == [None, None]


def test_mosaic_counts_need_one_value_per_cell() -> None:
    with pytest.raises(ValidationError, match="one value per x and y label"):
        EdaMosaicCounts.model_validate(
            {
                "xLabel": ["a", "b"],
                "yLabel": [["x", "y"], ["x", "y"]],
                "value": [[1, 2], [3]],
            }
        )


def test_a_faceted_mosaic_is_refused() -> None:
    table = {"xLabel": ["a"], "yLabel": [["x"]], "value": [[1]]}
    with pytest.raises(ValidationError, match="exactly one table"):
        EdaContTableResponse.model_validate(
            {"mosaic": {"data": [table, table], "config": _CONFIG}}
        )


def test_a_mosaic_with_two_statistics_rows_is_refused() -> None:
    table = {"xLabel": ["a"], "yLabel": [["x"]], "value": [[1]]}
    with pytest.raises(ValidationError, match="at most one statistics row"):
        EdaContTableResponse.model_validate(
            {
                "mosaic": {"data": [table], "config": _CONFIG},
                "statsTable": [{"chisq": 1}, {"chisq": 2}],
            }
        )


def test_a_mosaic_without_statistics_has_none() -> None:
    table = {"xLabel": ["a"], "yLabel": [["x"]], "value": [[1]]}

    parsed = EdaContTableResponse.model_validate(
        {"mosaic": {"data": [table], "config": _CONFIG}}
    )

    assert parsed.counts.value == [[1]]
    assert (parsed.chisq, parsed.pvalue, parsed.degrees_freedom) == (None, None, None)


def test_a_boxplot_response_without_its_envelope_is_refused() -> None:
    with pytest.raises(ValidationError, match="data"):
        EdaBoxplotResponse.model_validate({"config": _CONFIG})


def test_a_configuration_with_a_comparator_is_the_de_member() -> None:
    parsed = COMPUTE_CONFIG.validate_python(
        {
            "identifierVariable": _SPEC,
            "valueVariable": _SPEC,
            "comparator": {
                "variable": _SPEC,
                "groupA": [{"label": "normal"}],
                "groupB": [{"label": "febrile"}],
            },
        }
    )

    assert isinstance(parsed, EdaDifferentialExpressionConfig)


def test_a_configuration_without_a_comparator_is_the_pca_member() -> None:
    parsed = COMPUTE_CONFIG.validate_python(
        {"identifierVariable": _SPEC, "valueVariable": _SPEC}
    )

    assert isinstance(parsed, EdaDimensionalityReductionConfig)
    assert parsed.data_format == "normalizedValues"
