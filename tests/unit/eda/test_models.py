from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from veupathdb.eda.models import (
    ANALYSIS_DESCRIPTION_BYTES,
    ANALYSIS_DISPLAY_NAME_BYTES,
    EdaAnalysisDescriptor,
    EdaComparator,
    EdaComputation,
    EdaComputationDescriptor,
    EdaComputeJob,
    EdaCountResponse,
    EdaDifferentialExpressionConfig,
    EdaDistributionResponse,
    EdaLabeledRange,
    EdaNewAnalysis,
    EdaPermissionsResponse,
    EdaStringSetFilter,
    EdaStudiesResponse,
    EdaStudyOverview,
    EdaSubsetDescriptor,
    EdaVariableSpec,
    EdaVisualization,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
    VolcanoStatsResponse,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR


def _load(name: str) -> object:
    return json.loads((FIXTURE_DIR / name).read_text())


def _config() -> EdaDifferentialExpressionConfig:
    return EdaDifferentialExpressionConfig(
        identifier_variable=EdaVariableSpec(
            entity_id="ENT_fd574cd6", variable_id="VEUPATHDB_GENE_ID"
        ),
        value_variable=EdaVariableSpec(
            entity_id="ENT_fd574cd6", variable_id="SEQUENCE_READ_COUNT_ANTISENSE"
        ),
        comparator=EdaComparator(
            variable=EdaVariableSpec(
                entity_id="ENT_8151325d", variable_id="VAR_081ab087"
            ),
            group_a=[EdaLabeledRange(label="normal")],
            group_b=[EdaLabeledRange(label="febrile")],
        ),
    )


def test_study_id_holds_a_dataset_id_and_keeps_the_upstream_name() -> None:
    analysis = EdaNewAnalysis(study_id="DS_e973eadd57", display_name="probe")
    dumped = analysis.model_dump(by_alias=True, exclude_none=True)
    assert dumped["studyId"] == "DS_e973eadd57"
    assert "datasetId" not in dumped


def test_a_long_display_name_is_cut_to_the_upstream_bound() -> None:
    """The user service refuses a displayName over 50 UTF-8 bytes."""
    purpose = (
        "Febrile versus normal differential expression in the LRR5 and DHC "
        "heat-shock RNA-seq study"
    )
    assert len(purpose) == 90
    analysis = EdaNewAnalysis(study_id="DS_e973eadd57", display_name=purpose)
    sent = analysis.model_dump(by_alias=True)["displayName"]
    assert sent == "Febrile versus normal differential expression in t"
    assert len(sent.encode()) == ANALYSIS_DISPLAY_NAME_BYTES


def test_a_display_name_cut_never_splits_a_multibyte_character() -> None:
    """A cut in the middle of a character drops it, so the name stays UTF-8."""
    name = f"{'a' * 48}→{'b' * 9}"
    assert len(name.encode()) == 60
    sent = EdaNewAnalysis(study_id="DS_x", display_name=name).display_name
    assert sent == "a" * 48
    assert len(sent.encode()) <= ANALYSIS_DISPLAY_NAME_BYTES
    assert sent.encode().decode() == sent


def test_a_display_name_within_the_bound_is_untouched() -> None:
    name = "a" * 49
    assert len(name.encode()) == 49
    assert EdaNewAnalysis(study_id="DS_x", display_name=name).display_name == name


def test_a_long_description_is_cut_to_the_upstream_bound() -> None:
    """The same route caps description at 4000 UTF-8 bytes."""
    analysis = EdaNewAnalysis(
        study_id="DS_x", display_name="probe", description="d" * 4100
    )
    assert len(analysis.description.encode()) == ANALYSIS_DESCRIPTION_BYTES


def test_derived_variables_hold_ids_not_specs() -> None:
    descriptor = EdaAnalysisDescriptor(derived_variables=["dv-abc-123"])
    assert descriptor.model_dump(by_alias=True)["derivedVariables"] == ["dv-abc-123"]


def test_a_derived_variable_spec_object_is_refused() -> None:
    """An inline object in that array is a 422 upstream."""
    with pytest.raises(ValidationError):
        EdaAnalysisDescriptor.model_validate(
            {"derivedVariables": [{"entityId": "E", "variableId": "V"}]}
        )


def test_an_empty_analysis_serializes_the_full_descriptor_skeleton() -> None:
    analysis = EdaNewAnalysis(study_id="DS_x", display_name="x")
    dumped = analysis.model_dump(by_alias=True, exclude_none=True)
    assert dumped["descriptor"] == {
        "subset": {"descriptor": [], "uiSettings": {}},
        "computations": [],
        "starredVariables": [],
        "dataTableConfig": {},
        "derivedVariables": [],
    }


def test_the_bridge_spec_round_trips_byte_for_byte() -> None:
    """The recorded spec of the measured 202-then-200 sequence."""
    analysis = EdaNewAnalysis(
        study_id="DS_e973eadd57",
        display_name="...",
        description="",
        is_public=False,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(),
            computations=[
                EdaComputation(
                    computation_id="de2",
                    descriptor=EdaComputationDescriptor(configuration=_config()),
                    visualizations=[
                        EdaVisualization(
                            visualization_id="v2",
                            display_name="Volcano",
                            descriptor=EdaVolcanoDescriptor(
                                configuration=EdaVolcanoConfiguration(
                                    effect_size_threshold=1.0,
                                    significance_threshold=0.05,
                                ),
                            ),
                        )
                    ],
                )
            ],
        ),
    )
    dumped = json.loads(analysis.model_dump_json(by_alias=True, exclude_none=True))
    computation = dumped["descriptor"]["computations"][0]
    assert computation["descriptor"]["type"] == "differentialexpression"
    assert (
        computation["descriptor"]["configuration"]["differentialExpressionMethod"]
        == "DESeq"
    )
    assert computation["descriptor"]["configuration"]["pValueFloor"] == "1e-200"
    viz = computation["visualizations"][0]["descriptor"]
    assert viz["type"] == "volcanoplot"
    assert viz["configuration"]["effectSizeThreshold"] == 1.0
    assert viz["configuration"]["significanceThreshold"] == 0.05
    assert viz["configuration"]["effectDirection"] == "upAndDown"


def test_deseq2_is_not_a_wire_value() -> None:
    """The frontend display name is DESeq2; the wire enum is DESeq."""
    with pytest.raises(ValidationError):
        EdaDifferentialExpressionConfig.model_validate(
            {
                "identifierVariable": {"entityId": "E", "variableId": "V"},
                "valueVariable": {"entityId": "E", "variableId": "W"},
                "comparator": {
                    "variable": {"entityId": "P", "variableId": "C"},
                    "groupA": [{"label": "a"}],
                    "groupB": [{"label": "b"}],
                },
                "differentialExpressionMethod": "DESeq2",
            }
        )


def test_a_labeled_range_may_carry_a_label_alone() -> None:
    group = EdaLabeledRange.model_validate({"label": "normal"})
    assert group.min is None
    assert group.max is None
    assert group.model_dump(by_alias=True, exclude_none=True) == {"label": "normal"}


def test_a_comparator_group_may_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        EdaComparator.model_validate(
            {
                "variable": {"entityId": "P", "variableId": "C"},
                "groupA": [],
                "groupB": [{"label": "b"}],
            }
        )


def test_a_subset_descriptor_holds_the_typed_filter_array() -> None:
    subset = EdaSubsetDescriptor.model_validate(
        {
            "descriptor": [
                {
                    "entityId": "GENE_PHENOTYPE_DATA_ENTITY",
                    "variableId": "VAR_035294d0",
                    "type": "stringSet",
                    "stringSet": ["P. berghei"],
                }
            ],
            "uiSettings": {},
        }
    )
    assert isinstance(subset.descriptor[0], EdaStringSetFilter)


def test_the_job_id_key_is_capital_i_capital_d() -> None:
    job = EdaComputeJob.model_validate(_load("compute_job_lookup.json"))
    assert len(job.job_id) == 32
    assert job.status in {
        "queued",
        "in-progress",
        "complete",
        "failed",
        "expired",
        "no-such-job",
    }


def test_queue_position_is_absent_when_a_job_starts_at_once() -> None:
    job = EdaComputeJob.model_validate({"jobID": "a" * 32, "status": "queued"})
    assert job.queue_position is None


def test_volcano_numbers_arrive_as_strings() -> None:
    parsed = VolcanoStatsResponse.model_validate(_load("volcano_statistics.json"))
    first = parsed.statistics[0]
    assert isinstance(first.effect_size, str)
    assert isinstance(first.p_value, str)
    assert parsed.effect_size_label == "log2(Fold Change)"
    assert parsed.p_value_floor == "1e-200"
    assert parsed.adjusted_p_value_floor is None


def test_a_volcano_row_may_omit_both_p_values() -> None:
    parsed = VolcanoStatsResponse.model_validate(
        {
            "effectSizeLabel": "log2(Fold Change)",
            "statistics": [
                {"effectSize": "-1.49447459261845", "pointID": "PF3D7_MIT04200"}
            ],
        }
    )
    row = parsed.statistics[0]
    assert row.point_id == "PF3D7_MIT04200"
    assert row.p_value is None
    assert row.adjusted_p_value is None


def test_the_point_id_key_is_capital_i_capital_d_on_the_wire() -> None:
    parsed = VolcanoStatsResponse.model_validate(
        {"statistics": [{"effectSize": "1.0", "pointID": "PF3D7_0100200"}]}
    )
    assert parsed.statistics[0].point_id == "PF3D7_0100200"


def test_count_response_carries_only_a_count() -> None:
    parsed = EdaCountResponse.model_validate(_load("count_unfiltered.json"))
    assert parsed.count == 4279


def test_a_categorical_distribution_has_no_subset_min_or_mean() -> None:
    parsed = EdaDistributionResponse.model_validate(
        _load("distribution_categorical.json")
    )
    assert parsed.statistics.subset_min is None
    assert parsed.statistics.subset_mean is None
    assert parsed.statistics.subset_size == 4279
    assert parsed.statistics.num_var_values == 8409
    labels = {bin_.bin_label for bin_ in parsed.histogram}
    assert "P. berghei" in labels


def test_bin_bounds_are_strings_even_for_a_numeric_variable() -> None:
    parsed = EdaDistributionResponse.model_validate(
        {
            "histogram": [
                {
                    "value": 13,
                    "binStart": "0.0",
                    "binEnd": "5.0",
                    "binLabel": "[0.0,5.0)",
                }
            ],
            "statistics": {
                "subsetSize": 48721,
                "subsetMin": 3.0,
                "subsetMax": 18.9,
                "subsetMean": 12.032154770825814,
                "numVarValues": 36570,
                "numDistinctValues": 174,
                "numDistinctEntityRecords": 36570,
                "numMissingCases": 12151,
            },
        }
    )
    assert parsed.histogram[0].bin_start == "0.0"
    assert parsed.statistics.subset_mean is not None


def test_study_overview_tolerates_a_missing_short_display_name() -> None:
    """shortDisplayName and description are declared required and are absent live."""
    overview = EdaStudyOverview.model_validate(
        {
            "id": "STUDY_ccab256dfb",
            "datasetId": "DS_ccab256dfb",
            "sha1hash": "ccab256dfb7c9562dfa35f36345348ad2f2d5dfa",
            "sourceType": "curated",
            "displayName": "S. cerevisiae transcriptomes",
            "lastModified": "2026-05-27T20:00:00-04:00",
        }
    )
    assert overview.short_display_name is None
    assert overview.description is None
    assert overview.dataset_id == "DS_ccab256dfb"


def test_study_overview_keeps_the_lowercase_sha1hash_key() -> None:
    """/studies spells it sha1hash; /permissions spells it sha1Hash."""
    overview = EdaStudyOverview.model_validate(
        {
            "id": "STUDY_x",
            "datasetId": "DS_x",
            "sha1hash": "abc",
            "sourceType": "curated",
            "displayName": "x",
            "lastModified": "2026-05-27T20:00:00-04:00",
        }
    )
    assert overview.sha1hash == "abc"
    assert overview.model_dump(by_alias=True)["sha1hash"] == "abc"


def test_a_user_study_carries_an_empty_sha1hash() -> None:
    parsed = EdaStudiesResponse.model_validate(_load("studies_list.json"))
    user_studies = [s for s in parsed.studies if s.source_type == "user_submitted"]
    assert user_studies
    assert all(s.sha1hash == "" for s in user_studies)
    assert all(s.dataset_id.startswith("EDAUD_") for s in user_studies)


def test_permission_entry_spells_the_hash_with_a_capital_h() -> None:
    parsed = EdaPermissionsResponse.model_validate(_load("permissions.json"))
    entry = parsed.per_dataset["DS_53f554ec6a"]
    assert entry.study_id == "STUDY_53f554ec6a"
    assert entry.sha1_hash
    assert entry.action_authorization.results_all is True


def test_permission_entries_that_omit_declared_required_fields_still_parse() -> None:
    """24 of 880 live entries omit shortDisplayName or description."""
    parsed = EdaPermissionsResponse.model_validate(_load("permissions.json"))
    sparse = [
        e
        for e in parsed.per_dataset.values()
        if e.short_display_name is None or e.description is None
    ]
    assert sparse, "the trimmed fixture must retain the sparse entries"


def test_an_unmodelled_extra_field_is_ignored() -> None:
    overview = EdaStudyOverview.model_validate(
        {
            "id": "STUDY_x",
            "datasetId": "DS_x",
            "sha1hash": "",
            "sourceType": "user_submitted",
            "displayName": "x",
            "lastModified": "2026-05-27T20:00:00-04:00",
            "somethingUpstreamAddedLater": 1,
        }
    )
    assert not hasattr(overview, "somethingUpstreamAddedLater")
