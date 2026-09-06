from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from veupathdb.eda.models import (
    EdaCategoryVariable,
    EdaCollection,
    EdaComputeJob,
    EdaCountResponse,
    EdaDistributionResponse,
    EdaEntity,
    EdaFilter,
    EdaLongitudeRangeFilter,
    EdaLongitudeVariable,
    EdaMultiFilter,
    EdaNumberVariable,
    EdaPermissionsResponse,
    EdaStringSetFilter,
    EdaStringVariable,
    EdaStudiesResponse,
    EdaStudyDetailResponse,
    EdaVariable,
    VolcanoStatsResponse,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

PROVENANCE = "provenance.json"
FILTER = TypeAdapter(EdaFilter)
FILTERS = TypeAdapter(list[EdaFilter])
VARIABLE = TypeAdapter(EdaVariable)

READERS: dict[str, type[BaseModel]] = {
    "studies_list.json": EdaStudiesResponse,
    "study_detail_de.json": EdaStudyDetailResponse,
    "study_detail_phenotype.json": EdaStudyDetailResponse,
    "permissions.json": EdaPermissionsResponse,
    "count_unfiltered.json": EdaCountResponse,
    "count_filtered.json": EdaCountResponse,
    "distribution_categorical.json": EdaDistributionResponse,
    "compute_job_lookup.json": EdaComputeJob,
    "volcano_statistics.json": VolcanoStatsResponse,
}


def test_every_fixture_file_has_a_reader() -> None:
    on_disk = {p.name for p in FIXTURE_DIR.glob("*.json")} - {PROVENANCE}
    assert on_disk == set(READERS)


@pytest.mark.parametrize("name", sorted(READERS))
def test_fixture_validates(name: str) -> None:
    """Every recorded response validates against the model that reads it."""
    raw = json.loads((FIXTURE_DIR / name).read_text())
    READERS[name].model_validate(raw)


def test_string_set_round_trips_the_wire_shape() -> None:
    raw = {
        "entityId": "GENE_PHENOTYPE_DATA_ENTITY",
        "variableId": "VAR_035294d0",
        "type": "stringSet",
        "stringSet": ["P. berghei"],
    }
    parsed = FILTER.validate_python(raw)
    assert isinstance(parsed, EdaStringSetFilter)
    assert parsed.model_dump(by_alias=True, exclude_none=True) == raw


def test_an_empty_string_set_is_refused_before_the_wire() -> None:
    """The service answers 400 'String set filter: >0 strings must be specified'."""
    with pytest.raises(ValidationError):
        FILTER.validate_python(
            {
                "entityId": "E",
                "variableId": "V",
                "type": "stringSet",
                "stringSet": [],
            }
        )


def test_longitude_range_uses_left_and_right() -> None:
    parsed = FILTER.validate_python(
        {
            "entityId": "GAZ_00000448",
            "variableId": "OBI_0001621",
            "type": "longitudeRange",
            "left": 15.0,
            "right": 16.0,
        }
    )
    assert isinstance(parsed, EdaLongitudeRangeFilter)
    assert parsed.left == 15.0
    assert parsed.right == 16.0


def test_multi_filter_sub_filters_carry_no_entity_and_no_type() -> None:
    raw = {
        "entityId": "EUPATH_0000096",
        "variableId": "EUPATH_0000321",
        "type": "multiFilter",
        "operation": "union",
        "subFilters": [
            {"variableId": "EUPATH_0015135", "stringSet": ["Yes"]},
            {"variableId": "EUPATH_0033376", "stringSet": ["Yes"]},
        ],
    }
    parsed = FILTER.validate_python(raw)
    assert isinstance(parsed, EdaMultiFilter)
    assert parsed.operation == "union"
    assert parsed.model_dump(by_alias=True, exclude_none=True) == raw


def test_multi_filter_refuses_an_empty_sub_filter_list() -> None:
    with pytest.raises(ValidationError):
        FILTER.validate_python(
            {
                "entityId": "E",
                "variableId": "V",
                "type": "multiFilter",
                "operation": "union",
                "subFilters": [],
            }
        )


def test_multi_filter_refuses_an_operation_outside_the_two() -> None:
    with pytest.raises(ValidationError):
        FILTER.validate_python(
            {
                "entityId": "E",
                "variableId": "V",
                "type": "multiFilter",
                "operation": "xor",
                "subFilters": [{"variableId": "C", "stringSet": ["Yes"]}],
            }
        )


def test_string_prefix_set_is_refused() -> None:
    """Schema-present, source-present, wire-absent: the deployed build 422s it."""
    with pytest.raises(ValidationError):
        FILTER.validate_python(
            {
                "entityId": "E",
                "variableId": "V",
                "type": "stringPrefixSet",
                "prefixSet": ["ab"],
            }
        )


def test_an_extra_property_on_a_filter_is_dropped() -> None:
    parsed = FILTER.validate_python(
        {
            "entityId": "E",
            "variableId": "V",
            "type": "stringSet",
            "stringSet": ["yes"],
            "extraJunk": 1,
        }
    )
    assert "extraJunk" not in parsed.model_dump(by_alias=True)


def test_a_filter_array_serializes_as_a_bare_list() -> None:
    raw = [
        {
            "entityId": "E",
            "variableId": "V1",
            "type": "stringSet",
            "stringSet": ["a"],
        },
        {
            "entityId": "E",
            "variableId": "V2",
            "type": "numberRange",
            "min": 0.0,
            "max": 100.0,
        },
    ]
    parsed = FILTERS.validate_python(raw)
    assert FILTERS.dump_python(parsed, by_alias=True, exclude_none=True) == raw


def test_type_discriminates_a_string_variable() -> None:
    parsed = VARIABLE.validate_python(
        {
            "id": "VAR_035294d0",
            "parentId": "GENE_PHENOTYPE_DATA_ENTITY",
            "providerLabel": "No Provider Label available",
            "displayName": "Species",
            "displayType": "default",
            "type": "string",
            "hideFrom": [],
            "dataShape": "categorical",
            "vocabulary": ["P. berghei", "P. falciparum", "P. yoelii"],
            "distinctValuesCount": 3,
            "isMultiValued": True,
        }
    )
    assert isinstance(parsed, EdaStringVariable)
    assert parsed.is_multi_valued is True
    assert parsed.vocabulary == ["P. berghei", "P. falciparum", "P. yoelii"]


def test_a_category_variable_carries_no_value_fields() -> None:
    parsed = VARIABLE.validate_python(
        {
            "id": "EUPATH_0000321",
            "parentId": "EUPATH_0000308",
            "providerLabel": "No Provider Label available",
            "displayName": "Diagnosis at discharge",
            "displayType": "multifilter",
            "displayOrder": 4,
            "type": "category",
            "hideFrom": [],
        }
    )
    assert isinstance(parsed, EdaCategoryVariable)
    assert parsed.type == "category"
    assert parsed.display_type == "multifilter"
    assert not hasattr(parsed, "vocabulary")
    assert not hasattr(parsed, "data_shape")


def test_is_category_is_not_modelled() -> None:
    """Declared required in the RAML, absent on all 66664 variables scanned."""
    parsed = VARIABLE.validate_python(
        {
            "id": "V",
            "displayName": "v",
            "providerLabel": "p",
            "displayType": "default",
            "type": "category",
            "hideFrom": [],
            "isCategory": "true",
        }
    )
    assert "isCategory" not in parsed.model_dump(by_alias=True)
    assert not hasattr(parsed, "is_category")


def test_distribution_defaults_carry_only_three_of_six_keys() -> None:
    parsed = VARIABLE.validate_python(
        {
            "id": "SEQUENCE_READ_COUNT",
            "displayName": "read count",
            "providerLabel": "p",
            "displayType": "default",
            "type": "number",
            "hideFrom": [],
            "dataShape": "continuous",
            "distributionDefaults": {
                "rangeMin": 0,
                "rangeMax": 1684173,
                "binWidth": 54329,
            },
        }
    )
    assert isinstance(parsed, EdaNumberVariable)
    assert parsed.distribution_defaults.display_range_min is None
    assert parsed.distribution_defaults.range_max == 1684173


def test_scale_is_not_modelled() -> None:
    parsed = VARIABLE.validate_python(
        {
            "id": "V",
            "displayName": "v",
            "providerLabel": "p",
            "displayType": "default",
            "type": "number",
            "hideFrom": [],
            "scale": "log2",
        }
    )
    assert "scale" not in parsed.model_dump(by_alias=True)
    assert not hasattr(parsed, "scale")


def test_longitude_is_its_own_type() -> None:
    parsed = VARIABLE.validate_python(
        {
            "id": "OBI_0001621",
            "displayName": "longitude",
            "providerLabel": "p",
            "displayType": "longitude",
            "type": "longitude",
            "hideFrom": [],
            "precision": 1.0,
        }
    )
    assert isinstance(parsed, EdaLongitudeVariable)
    assert parsed.type == "longitude"
    assert parsed.precision == 1.0


def test_an_unknown_variable_type_is_refused() -> None:
    with pytest.raises(ValidationError):
        VARIABLE.validate_python(
            {
                "id": "V",
                "displayName": "v",
                "providerLabel": "p",
                "displayType": "default",
                "type": "geoaggregator",
                "hideFrom": [],
            }
        )


def test_the_entity_tree_is_recursive_and_children_are_optional() -> None:
    raw = json.loads((FIXTURE_DIR / "study_detail_de.json").read_text())
    detail = EdaStudyDetailResponse.model_validate(raw).study
    root = detail.root_entity
    assert root.id_column_name.endswith("_stable_id")
    assert root.children, "the DE study has a child counts entity"
    leaf = root.children[0]
    assert leaf.children == []
    assert isinstance(leaf, EdaEntity)


def test_normalization_method_null_is_a_string_value_not_absence() -> None:
    collection = EdaCollection.model_validate(
        {
            "id": "EUPATH_0005051",
            "displayName": "Eigengene",
            "type": "number",
            "dataShape": "continuous",
            "memberVariableIds": ["VAR_a", "VAR_b"],
            "imputeZero": False,
            "normalizationMethod": "NULL",
            "isCompositional": False,
            "isProportion": False,
            "member": "eigengene",
            "memberPlural": "eigengenes",
        }
    )
    assert collection.normalization_method == "NULL"
