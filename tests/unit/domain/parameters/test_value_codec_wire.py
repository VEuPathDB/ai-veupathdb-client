"""The eleven parameter kinds, and the literal string each puts in
``searchConfig.parameters``.

``JsonKeys`` declares eleven ``*_PARAM_TYPE`` constants and ``wdk-client``'s
``Parameter`` union is the same eleven. ``displayType`` is a separate axis.
"""

from __future__ import annotations

import json
from typing import get_args

import pytest
from pydantic import ValidationError as PydanticValidationError

from veupathdb.domain.parameters.value_codec import (
    _SCALAR_KINDS,
    _SCALAR_VALUE_BY_KIND,
    _WIRE_BUILDERS,
    as_param_kind,
    from_wire,
    wire_map,
)
from veupathdb.domain.parameters.values import (
    DateRangeValue,
    DateValue,
    FilterTermClause,
    FilterValue,
    InputDatasetValue,
    InputStepValue,
    MultiPickValue,
    NumberRangeValue,
    NumberValue,
    ParamKind,
    ParamValue,
    SinglePickValue,
    StringValue,
    TimestampValue,
)
from veupathdb.domain.parameters.wdk_vocab import vocab_keys
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse

_THE_ELEVEN = frozenset(
    {
        "string",
        "number",
        "number-range",
        "date",
        "date-range",
        "timestamp",
        "single-pick-vocabulary",
        "multi-pick-vocabulary",
        "filter",
        "input-dataset",
        "input-step",
    }
)

_ONE_OF_EVERY_KIND: dict[str, ParamValue] = {
    "a_string": StringValue(value="kinase"),
    "a_number": NumberValue(value=42),
    "a_number_range": NumberRangeValue(min=1, max=2),
    "a_date": DateValue(value="2026-01-01"),
    "a_date_range": DateRangeValue(min="2026-01-01", max="2026-12-31"),
    "a_timestamp": TimestampValue(value="1766000000000"),
    "a_single_pick": SinglePickValue(value="Gene"),
    "a_multi_pick": MultiPickValue(values=["product", "name"]),
    "a_filter": FilterValue(filters=[FilterTermClause(field="organism")]),
    "an_input_dataset": InputDatasetValue(dataset_id="558341"),
    "an_input_step": InputStepValue(step_id="440085983"),
}


def _genes_by_location() -> WDKSearchResponse:
    return WDKSearchResponse.model_validate(
        load_recorded("search_genes_by_location").json_body()
    )


class TestWdkParam001ElevenTypes:
    def test_wdk_param_001_param_kind_is_exactly_the_eleven(self) -> None:
        assert frozenset(get_args(ParamKind)) == _THE_ELEVEN

    def test_wdk_param_001_display_type_is_a_separate_axis(self) -> None:
        # organismSinglePick is a multi-pick parameter drawn as a select.
        params = {p.name: p for p in _genes_by_location().search_data.parameters or []}

        assert params["organismSinglePick"].type == "multi-pick-vocabulary"
        assert params["organismSinglePick"].display_type == "select"

    def test_wdk_param_001_a_select_multi_pick_still_sends_a_list(self) -> None:
        params = {p.name: p for p in _genes_by_location().search_data.parameters or []}
        kind = as_param_kind(params["organismSinglePick"].type)

        value = from_wire(kind, json.dumps(["Plasmodium falciparum 3D7"]))

        assert value == MultiPickValue(values=["Plasmodium falciparum 3D7"])

    def test_wdk_param_001_every_declared_type_is_one_of_the_eleven(self) -> None:
        declared = {p.type for p in _genes_by_location().search_data.parameters or []}

        assert declared <= _THE_ELEVEN


class TestWdkMap001DriftIsNoticedInBothDirections:
    def test_wdk_map_001_a_twelfth_kind_is_refused_by_name(self) -> None:
        with pytest.raises(PydanticValidationError):
            as_param_kind("gene-list")

    def test_wdk_map_001_a_twelfth_kind_has_no_wire_form(self) -> None:
        with pytest.raises(PydanticValidationError):
            from_wire("gene-list", "anything")  # type: ignore[arg-type]

    def test_wdk_map_001_every_kind_has_a_way_to_build_a_value(self) -> None:
        # Removing a member is caught by mypy over these three maps; adding one
        # is caught here.
        covered = (
            frozenset(_WIRE_BUILDERS) | _SCALAR_KINDS | frozenset(_SCALAR_VALUE_BY_KIND)
        )

        assert covered == _THE_ELEVEN

    def test_wdk_map_001_every_kind_round_trips_from_a_wire_string(self) -> None:
        wire_by_kind: dict[str, str] = {
            "string": "kinase",
            "number": "42",
            "number-range": '{"min": 1, "max": 2}',
            "date": "2026-01-01",
            "date-range": '{"min": "2026-01-01", "max": "2026-12-31"}',
            "timestamp": "1766000000000",
            "single-pick-vocabulary": "Gene",
            "multi-pick-vocabulary": '["product"]',
            "filter": '{"filters": []}',
            "input-dataset": "558341",
            "input-step": "440085983",
        }

        assert frozenset(wire_by_kind) == _THE_ELEVEN
        for kind, wire in wire_by_kind.items():
            assert from_wire(as_param_kind(kind), wire).type == kind


class TestWdkParam002EveryValueIsAString:
    """WDK-PARAM-002: the structured kinds are stringified into the map."""

    def test_wdk_param_002_every_kind_encodes_to_a_string(self) -> None:
        encoded = wire_map(_ONE_OF_EVERY_KIND)

        assert [type(v) for v in encoded.values()] == [str] * len(_ONE_OF_EVERY_KIND)

    def test_wdk_param_002_the_structured_kinds_carry_json_in_the_string(self) -> None:
        encoded = wire_map(_ONE_OF_EVERY_KIND)

        assert json.loads(encoded["a_number_range"]) == {"min": 1, "max": 2}
        assert json.loads(encoded["a_date_range"]) == {
            "min": "2026-01-01",
            "max": "2026-12-31",
        }
        assert json.loads(encoded["a_multi_pick"]) == ["product", "name"]
        assert json.loads(encoded["a_filter"])["filters"][0]["field"] == "organism"

    def test_wdk_param_002_a_json_object_is_never_nested_in_the_map(self) -> None:
        # A map value that is an object rather than a string is a 400 from the
        # properties parser, which reads every value with getString.
        encoded = wire_map(_ONE_OF_EVERY_KIND)

        assert json.loads(json.dumps(encoded)) == encoded


class TestWdkParam003SinglePickIsABareTerm:
    """WDK-PARAM-003: a bare term, never an array, never quoted."""

    def test_wdk_param_003_a_single_pick_wire_value_is_the_bare_term(self) -> None:
        assert SinglePickValue(value="Gene").to_wire() == "Gene"

    def test_wdk_param_003_a_single_pick_is_not_json_encoded(self) -> None:
        # `["Gene"]` means the same thing to WDK; `"Gene"` with quotes does not.
        assert not SinglePickValue(value="Gene").to_wire().startswith(("[", '"'))

    def test_wdk_param_003_a_term_containing_a_comma_survives_intact(self) -> None:
        # Single-pick does not split on commas, and `2,-3` is a real term.
        assert SinglePickValue(value="2,-3").to_wire() == "2,-3"

    def test_wdk_param_003_two_terms_are_not_expressible(self) -> None:
        # Two elements is an unhandled WdkRuntimeException, so the type holds one.
        with pytest.raises(PydanticValidationError):
            SinglePickValue(value=["Gene", "Transcript"])  # type: ignore[arg-type]

    def test_wdk_param_003_the_wire_value_is_one_of_the_declared_terms(self) -> None:
        search = WDKSearchResponse.model_validate(
            load_recorded("search_genes_by_exon_count").json_body()
        ).search_data
        scope = next(p for p in search.parameters or [] if p.name == "scope")

        assert scope.type == "single-pick-vocabulary"
        assert vocab_keys(scope.vocabulary) == {"Gene", "Transcript"}
        assert SinglePickValue(value="Gene").to_wire() in vocab_keys(scope.vocabulary)


class TestWdkParam009HandlesAreBareIssuedIds:
    """WDK-PARAM-009: an input value is an id WDK issued, sent bare."""

    def test_wdk_param_009_an_input_step_wire_value_is_the_bare_id(self) -> None:
        assert InputStepValue(step_id="440085983").to_wire() == "440085983"

    def test_wdk_param_009_an_input_step_id_is_read_back_by_long_parse_long(
        self,
    ) -> None:
        assert int(InputStepValue(step_id="440085983").to_wire()) == 440085983

    def test_wdk_param_009_an_input_dataset_wire_value_is_the_bare_id(self) -> None:
        assert InputDatasetValue(dataset_id="558341").to_wire() == "558341"

    def test_wdk_param_009_neither_handle_is_json_encoded(self) -> None:
        assert InputStepValue(step_id="7").to_wire() == "7"
        assert InputDatasetValue(dataset_id="7").to_wire() == "7"

    def test_wdk_param_009_an_empty_handle_is_not_expressible(self) -> None:
        # Empty is what WDK reports before a wiring, and it is WDK's to write.
        with pytest.raises(PydanticValidationError):
            InputStepValue(step_id="")
        with pytest.raises(PydanticValidationError):
            InputDatasetValue(dataset_id="")
