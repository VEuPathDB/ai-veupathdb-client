"""What a step, a step tree, an answer and a record are made of.

A step's kind is the number of answer parameters its search declares. A
negative estimated size is the absence of a count, not a count, and one count
means the records you got. ``recordClassName`` names two different things in
one response body.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from veupathdb.domain.strategy.ops import BOOLEAN_OPERATORS, CombineOp, parse_op
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import (
    CombinedStepSpec,
    WDKAnswer,
    WDKAnswerMeta,
    WDKSearch,
    WDKSearchResponse,
    WDKStep,
    WDKStepTree,
)

_BOOLEAN_OPERATOR_VALUES = [
    "INTERSECT",
    "LONLY",
    "MINUS",
    "RMINUS",
    "RONLY",
    "UNION",
]

_LINK: dict[str, str] = {
    "url": "/a/app/record/gene/PF3D7_0100100",
    "displayText": "PF3D7_0100100",
}
_EMPTY_LINK: dict[str, str] = {"url": "/a/app/record/gene/x", "displayText": ""}

_ANSWER: dict[str, Any] = {
    "meta": {
        "totalCount": 1,
        "responseCount": 1,
        "recordClassName": "transcript",
    },
    "records": [
        {
            "displayName": "PF3D7_0100100",
            "id": [{"name": "source_id", "value": "PF3D7_0100100"}],
            "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
            "attributes": {
                "source_id": "PF3D7_0100100",
                "gene_link": _LINK,
                "product": None,
                "organism": "<i>Plasmodium falciparum</i> 3D7",
                "empty_link": _EMPTY_LINK,
            },
        }
    ],
}

_STEP_SPEC: dict[str, Any] = {
    "id": 1,
    "searchName": "GenesByX",
    "searchConfig": {"parameters": {}},
}


def _answer() -> WDKAnswer:
    return WDKAnswer.model_validate(_ANSWER)


def _step(**extra: object) -> WDKStep:
    return WDKStep.model_validate({**_STEP_SPEC, **extra})


def _combined(**overrides: object) -> CombinedStepSpec:
    return CombinedStepSpec.model_validate(
        {
            "primaryStepId": 1,
            "secondaryStepId": 2,
            "booleanOperator": "INTERSECT",
            **overrides,
        }
    )


def _search(name: str) -> WDKSearch:
    return WDKSearchResponse.model_validate(load_recorded(name).json_body()).search_data


def _input_step_names(search: WDKSearch) -> list[str]:
    return [p.name for p in search.parameters or [] if p.type == "input-step"]


class TestCombinedStepSpecOperator:
    def test_accepts_every_boolean_operator(self) -> None:
        for operator in BOOLEAN_OPERATORS:
            assert (
                _combined(booleanOperator=operator.value).boolean_operator is operator
            )

    def test_rejects_colocate(self) -> None:
        # COLOCATE is not a boolean operator: WDK does it through
        # GenesBySpanLogic, so it must never reach the boolean search.
        with pytest.raises(ValidationError, match="COLOCATE"):
            _combined(booleanOperator="COLOCATE")

    def test_rejects_an_operator_wdk_does_not_have(self) -> None:
        with pytest.raises(ValidationError):
            _combined(booleanOperator="INTERSCET")

    def test_a_plain_string_becomes_the_enum(self) -> None:
        assert _combined(booleanOperator="UNION").boolean_operator is CombineOp.UNION


class TestCombinedStepSpecDisplayFields:
    def test_inherits_the_patch_spec_display_fields(self) -> None:
        spec = _combined(customName="INTERSECT controls")
        assert spec.custom_name == "INTERSECT controls"

    def test_display_fields_are_optional(self) -> None:
        assert "customName" not in _combined().model_dump(
            by_alias=True, exclude_none=True
        )
        assert _combined().custom_name is None

    def test_weight_defaults_to_unset(self) -> None:
        assert "wdkWeight" not in _combined().model_dump(
            by_alias=True, exclude_none=True
        )
        assert _combined().wdk_weight is None

    def test_weight_is_carried(self) -> None:
        assert _combined(wdkWeight=7).wdk_weight == 7


class TestCombinedStepSpecInputs:
    def test_both_inputs_are_required(self) -> None:
        with pytest.raises(ValidationError):
            CombinedStepSpec.model_validate({"booleanOperator": "INTERSECT"})

    def test_inputs_are_carried(self) -> None:
        spec = _combined(primaryStepId=41, secondaryStepId=42)
        assert (spec.primary_step_id, spec.secondary_step_id) == (41, 42)


class TestANegativeSizeIsNotACount:
    def test_minus_one_reads_as_no_count(self) -> None:
        assert (
            _step(estimatedSize=-1).estimated_size,
            _step(estimatedSize=0).estimated_size,
        ) == (
            None,
            0,
        )

    def test_any_negative_reads_as_no_count(self) -> None:
        assert (
            _step(estimatedSize=-42).estimated_size,
            _step(estimatedSize=42).estimated_size,
        ) == (None, 42)


class TestARealCountSurvives:
    def test_zero_is_a_real_result(self) -> None:
        # A search that matched nothing is a scientific finding, not a gap.
        assert _step(estimatedSize=0).estimated_size == 0

    def test_a_positive_count_is_kept(self) -> None:
        assert _step(estimatedSize=3392).estimated_size == 3392


class TestAbsence:
    def test_an_omitted_key_reads_as_no_count(self) -> None:
        assert "estimatedSize" not in _STEP_SPEC
        assert _step().estimated_size is None


@pytest.mark.parametrize("size", [-1, -2, -1000])
def test_no_negative_ever_reaches_a_caller(size: int) -> None:
    value = _step(estimatedSize=size).estimated_size
    assert value is None or value >= 0


class TestTheCountMatchesTheRecords:
    def test_the_view_filtered_display_count_wins(self) -> None:
        meta = WDKAnswerMeta(
            totalCount=2407,
            displayTotalCount=2400,
            viewTotalCount=4,
            displayViewTotalCount=4,
        )

        assert meta.records_returned() == 4

    def test_the_unfiltered_count_is_not_used_when_a_view_filter_applies(self) -> None:
        meta = WDKAnswerMeta(
            totalCount=2407,
            displayTotalCount=2400,
            viewTotalCount=4,
            displayViewTotalCount=4,
        )

        assert meta.records_returned() != meta.total_count

    def test_without_a_view_filter_all_four_agree(self) -> None:
        meta = WDKAnswerMeta(
            totalCount=2407,
            displayTotalCount=2407,
            viewTotalCount=2407,
            displayViewTotalCount=2407,
        )

        assert meta.records_returned() == 2407


class TestAbsenceIsNotZero:
    def test_an_absent_count_falls_back_to_the_next_one(self) -> None:
        meta = WDKAnswerMeta(totalCount=2407)

        assert meta.records_returned() == 2407

    def test_all_absent_raises_rather_than_reporting_zero(self) -> None:
        with pytest.raises(ValueError, match="no result count"):
            WDKAnswerMeta().records_returned()

    def test_a_genuine_zero_is_reported_as_zero(self) -> None:
        meta = WDKAnswerMeta(
            totalCount=0,
            displayTotalCount=0,
            viewTotalCount=0,
            displayViewTotalCount=0,
        )

        assert meta.records_returned() == 0


class TestTheTwoRecordClassNames:
    def test_meta_carries_the_url_segment(self) -> None:
        assert _answer().meta.record_class_name == "transcript"

    def test_a_record_carries_the_full_name(self) -> None:
        record = _answer().records[0]

        assert (
            record.record_class_name == "TranscriptRecordClasses.TranscriptRecordClass"
        )

    def test_one_is_not_the_other(self) -> None:
        answer = _answer()

        assert answer.meta.record_class_name != answer.records[0].record_class_name


class TestAnAttributeValueIsNotAlwaysAString:
    def test_a_plain_value_is_a_string(self) -> None:
        assert _answer().records[0].attributes["source_id"] == "PF3D7_0100100"

    def test_a_link_value_stays_an_object(self) -> None:
        # The url is what a reader clicks, so it must survive to the client.
        assert _answer().records[0].attributes["gene_link"] == _LINK

    def test_an_absent_value_is_null(self) -> None:
        assert "product" in _ANSWER["records"][0]["attributes"]
        assert _answer().records[0].attributes["product"] is None

    def test_markup_is_not_stripped(self) -> None:
        assert "<i>" in str(_answer().records[0].attributes["organism"])


class TestComparingAnAttributeToText:
    def test_a_plain_value_compares_by_itself(self) -> None:
        assert _answer().records[0].attribute_text("source_id") == "PF3D7_0100100"

    def test_a_link_value_compares_by_its_display_text(self) -> None:
        assert _answer().records[0].attribute_text("gene_link") == "PF3D7_0100100"

    def test_a_null_value_has_no_text(self) -> None:
        record = _answer().records[0]

        assert (record.attributes["product"], record.attribute_text("product")) == (
            None,
            None,
        )

    def test_a_link_without_display_text_has_no_text(self) -> None:
        record = _answer().records[0]

        assert record.attributes["empty_link"] == _EMPTY_LINK
        assert record.attribute_text("empty_link") is None

    def test_an_attribute_that_was_not_requested_has_no_text(self) -> None:
        record = _answer().records[0]

        assert "molecular_weight" not in record.attributes
        assert record.attribute_text("molecular_weight") is None


class TestWdkStep001KindIsTheAnswerParameterCount:
    def test_wdk_step_001_a_leaf_declares_no_answer_parameter(self) -> None:
        assert _input_step_names(_search("search_genes_by_molecular_weight")) == []

    def test_wdk_step_001_a_transform_declares_one(self) -> None:
        assert _input_step_names(_search("search_genes_by_orthologs")) == [
            "gene_result"
        ]

    def test_wdk_step_001_a_combined_step_declares_two(self) -> None:
        names = _input_step_names(_search("search_boolean_transcript"))

        assert len(names) == 2

    def test_wdk_step_001_an_input_parameter_has_no_naming_convention(self) -> None:
        # `bq_left_op_*` is specific to the generated boolean query.
        transform = _search("search_genes_by_orthologs")

        assert _input_step_names(transform) == ["gene_result"]
        assert not any(n.startswith("bq_") for n in _input_step_names(transform))

    def test_wdk_step_001_the_order_of_declaration_is_the_slot_order(self) -> None:
        # Ordinal 0 is the primary input, ordinal 1 the secondary.
        left, right = _input_step_names(_search("search_boolean_transcript"))

        assert left.startswith("bq_left_op_")
        assert right.startswith("bq_right_op_")


class TestWdkStep006OperandNamesEmbedTheFullName:
    def test_wdk_step_006_the_operand_names_carry_the_record_class_full_name(
        self,
    ) -> None:
        search = _search("search_boolean_transcript")

        assert search.param_names == [
            "bq_left_op_TranscriptRecordClasses_TranscriptRecordClass",
            "bq_right_op_TranscriptRecordClasses_TranscriptRecordClass",
            "bq_operator",
        ]

    def test_wdk_step_006_the_operator_name_is_a_bare_constant(self) -> None:
        search = _search("search_boolean_transcript")

        assert "bq_operator" in search.param_names

    def test_wdk_step_006_the_step_reports_the_url_segment_instead(self) -> None:
        # There is no string transformation from one to the other.
        search = _search("search_boolean_transcript")

        assert search.output_record_class_name == "transcript"
        assert "transcript" not in search.param_names[0].removeprefix("bq_left_op_")


class TestWdkStep008BothOperandsAreOneRecordClass:
    def test_wdk_step_008_the_allowed_inputs_are_the_same_single_class(self) -> None:
        search = _search("search_boolean_transcript")

        assert search.allowed_primary_input_record_class_names == ["transcript"]
        assert search.allowed_secondary_input_record_class_names == ["transcript"]

    def test_wdk_step_008_the_result_is_that_same_class(self) -> None:
        assert _search("search_boolean_transcript").output_record_class_name == (
            "transcript"
        )

    def test_wdk_step_008_colocation_is_not_a_boolean_operator(self) -> None:
        # Colocation relates different kinds of thing, so it is excluded.
        assert sorted(op.value for op in BOOLEAN_OPERATORS) == _BOOLEAN_OPERATOR_VALUES
        assert CombineOp.COLOCATE not in BOOLEAN_OPERATORS
        assert CombineOp.INTERSECT in BOOLEAN_OPERATORS

    def test_wdk_step_008_the_operator_terms_are_the_vocabulary_terms(self) -> None:
        # Send MINUS, not LEFT_MINUS: display and term differ on four of six.
        assert parse_op("LEFT_MINUS") is CombineOp.MINUS
        assert CombineOp.MINUS.value == "MINUS"


class TestWdkStrat001ANodeCarriesAStepIdAndNothingElse:
    def test_wdk_strat_001_a_leaf_node_serializes_to_one_key(self) -> None:
        node = WDKStepTree(stepId=7)

        assert node.model_dump(by_alias=True, exclude_none=True) == {"stepId": 7}

    def test_wdk_strat_001_a_combined_node_carries_its_two_inputs(self) -> None:
        node = WDKStepTree(
            stepId=3,
            primaryInput=WDKStepTree(stepId=1),
            secondaryInput=WDKStepTree(stepId=2),
        )

        assert node.model_dump(by_alias=True, exclude_none=True) == {
            "stepId": 3,
            "primaryInput": {"stepId": 1},
            "secondaryInput": {"stepId": 2},
        }

    def test_wdk_strat_001_no_step_data_rides_on_the_tree(self) -> None:
        # The tempting shape is a tree of whole steps; every read then has two
        # copies of a step's data.
        keys = set(WDKStepTree.model_fields)

        assert keys == {"step_id", "primary_input", "secondary_input"}
