from __future__ import annotations

import pytest
from pydantic import ValidationError

from veupathdb.domain.wdk_values import WDKHistogramStatistics
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import (
    WDKAttributeField,
    WDKRecordType,
    WDKSearchResponse,
)


@pytest.mark.skipif(
    needs_qa_recording("wdk/record_type_build.json"), reason=NEEDS_QA_RECORDING
)
def test_an_expanded_record_type_names_each_column_data_type() -> None:
    record_type = WDKRecordType.model_validate(
        load_recorded("record_type_build").json_body()
    )

    assert [(a.name, a.column_data_type) for a in record_type.attributes or []] == [
        ("primary_key", "STRING"),
        ("build_number", "STRING"),
        ("release_date", "DATE"),
    ]
    assert {
        (a.name, a.column_data_type)
        for search in record_type.searches or []
        for a in search.dynamic_attributes
    } == {("wdk_weight", "NUMBER")}


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_location.json"), reason=NEEDS_QA_RECORDING
)
def test_a_search_names_each_dynamic_column_data_type() -> None:
    search = WDKSearchResponse.model_validate(
        load_recorded("search_genes_by_location").json_body()
    ).search_data

    assert [(a.name, a.column_data_type) for a in search.dynamic_attributes] == [
        ("dynamic_location", "STRING"),
        ("matched_result", "STRING"),
        ("wdk_weight", "NUMBER"),
    ]


def test_an_expanded_column_without_a_data_type_is_refused() -> None:
    with pytest.raises(ValidationError, match="columnDataType"):
        WDKAttributeField.model_validate({"name": "organism"})


def test_a_data_type_outside_the_wdk_enum_is_refused() -> None:
    with pytest.raises(ValidationError, match="columnDataType"):
        WDKAttributeField.model_validate(
            {"name": "organism", "columnDataType": "string"}
        )


def test_a_date_column_reads_its_statistics_as_dates() -> None:
    statistics = WDKHistogramStatistics.model_validate(
        {
            "subsetSize": 3,
            "subsetMin": "2019-04-01T00:00:00",
            "subsetMax": "2024-10-01T00:00:00",
            "subsetMean": "2022-01-15T00:00:00",
            "numVarValues": 3,
            "numDistinctValues": 3,
            "numDistinctEntityRecords": 3,
            "numMissingCases": 0,
        }
    )

    assert (
        statistics.subset_min,
        statistics.subset_max,
        statistics.subset_mean,
    ) == ("2019-04-01T00:00:00", "2024-10-01T00:00:00", "2022-01-15T00:00:00")


def test_a_number_column_reads_its_statistics_as_numbers() -> None:
    statistics = WDKHistogramStatistics.model_validate(
        {"subsetSize": 2, "subsetMin": 2, "subsetMax": 22.0, "subsetMean": 4.5}
    )

    assert (
        statistics.subset_min,
        statistics.subset_max,
        statistics.subset_mean,
    ) == (2.0, 22.0, 4.5)
