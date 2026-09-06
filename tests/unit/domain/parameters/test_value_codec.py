"""Coercion into typed parameter values, and the shapes WDK accepts for each."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError as PydanticValidationError

from veupathdb.domain.parameters.value_codec import (
    _PARAM_VALUE_ADAPTER,
    coerce_context_values,
    coerce_param_value,
    param_value_from_raw,
)
from veupathdb.domain.parameters.values import (
    FilterTermClause,
    FilterValue,
    MultiPickValue,
    NumberRangeValue,
    NumberValue,
    SinglePickValue,
    StringValue,
)


class TestCoerceContextValues:
    def test_coerce_context_values_by_shape(self) -> None:
        out = coerce_context_values(
            {
                "profileset_generic": "SRP047470 ... DESeq",
                "samples": ["Adult_female", "Adult_male"],
                "typed": {"type": "string", "value": "x"},
            }
        )
        assert out["profileset_generic"] == SinglePickValue(value="SRP047470 ... DESeq")
        assert out["samples"] == MultiPickValue(values=["Adult_female", "Adult_male"])
        assert out["typed"] == StringValue(value="x")

    def test_coerce_context_values_passes_instances(self) -> None:
        out = coerce_context_values({"p": SinglePickValue(value="v")})
        assert out["p"] == SinglePickValue(value="v")


class TestFromRaw:
    def test_from_raw_string_scalar(self) -> None:
        assert param_value_from_raw("odorant binding protein", "string") == StringValue(
            value="odorant binding protein"
        )

    def test_from_raw_number_accepts_int_and_str(self) -> None:
        assert param_value_from_raw(2, "number") == NumberValue(value=2.0)
        assert param_value_from_raw("2", "number") == NumberValue(value=2.0)

    def test_from_raw_single_pick(self) -> None:
        assert param_value_from_raw(
            "Aedes aegypti", "single-pick-vocabulary"
        ) == SinglePickValue(value="Aedes aegypti")

    def test_from_raw_multi_pick_scalar_and_list(self) -> None:
        assert param_value_from_raw(
            "InterPro", "multi-pick-vocabulary"
        ) == MultiPickValue(values=["InterPro"])
        assert param_value_from_raw(
            ["InterPro", "product"], "multi-pick-vocabulary"
        ) == MultiPickValue(values=["InterPro", "product"])

    def test_from_raw_passes_through_already_typed(self) -> None:
        assert param_value_from_raw({"type": "string", "value": "x"}, "string") == (
            StringValue(value="x")
        )

    def test_from_raw_number_range_from_dict(self) -> None:
        value = param_value_from_raw({"min": 1, "max": 5}, "number-range")
        assert value == NumberRangeValue(min=1.0, max=5.0)


class TestCoerceParamValue:
    def test_coerce_identity_returns_same_value(self) -> None:
        value = StringValue(value="x")
        assert coerce_param_value(value, "string") is value

    def test_coerce_integer_number_to_string(self) -> None:
        assert coerce_param_value(NumberValue(value=2.0), "string") == StringValue(
            value="2"
        )

    def test_coerce_float_number_to_string(self) -> None:
        assert coerce_param_value(NumberValue(value=1.5), "string") == StringValue(
            value="1.5"
        )

    def test_coerce_numeric_string_to_number(self) -> None:
        assert coerce_param_value(StringValue(value="1.5"), "number") == NumberValue(
            value=1.5
        )

    def test_coerce_string_to_single_pick(self) -> None:
        assert coerce_param_value(
            StringValue(value="Pf3D7"), "single-pick-vocabulary"
        ) == SinglePickValue(value="Pf3D7")

    def test_coerce_rejects_multipick_to_string(self) -> None:
        with pytest.raises(ValueError, match="not valid"):
            coerce_param_value(MultiPickValue(values=["a"]), "string")

    def test_coerce_rejects_scalar_to_range(self) -> None:
        with pytest.raises(ValueError, match="not valid"):
            coerce_param_value(NumberValue(value=1.0), "number-range")


class TestTheEmptyMultiPick:
    """A multi-pick parameter must be able to say "nothing selected".

    The literal string "[]" reached vocabulary matching and was rejected on a
    parameter whose own spec sets allowEmptyValue=true. Whether an empty
    selection is allowed is a per-parameter question answered by the spec.
    """

    def test_empty_selection_is_representable(self) -> None:
        assert MultiPickValue(values=[]).values == []

    def test_empty_selection_serializes_to_an_empty_json_array(self) -> None:
        assert MultiPickValue(values=[]).to_wire() == "[]"

    def test_empty_selection_decodes_to_an_empty_list(self) -> None:
        assert MultiPickValue(values=[]).to_decoded() == []

    def test_empty_selection_round_trips_through_parse(self) -> None:
        raw = json.loads(MultiPickValue(values=[]).model_dump_json(by_alias=True))
        assert _PARAM_VALUE_ADAPTER.validate_python(raw) == MultiPickValue(values=[])

    def test_non_empty_selection_still_works(self) -> None:
        value = MultiPickValue(values=["bant", "bsub"])
        assert value.to_decoded() == ["bant", "bsub"]
        assert json.loads(value.to_wire()) == ["bant", "bsub"]

    def test_values_must_still_be_strings(self) -> None:
        with pytest.raises(PydanticValidationError):
            MultiPickValue(values=[{"nope": 1}])  # type: ignore[list-item]


class TestTheFilterValue:
    """``BaseFilter`` = {field, type, isRange, includeUnknown, value}; an empty
    filter list is "include all"."""

    def test_empty_filter_is_include_all(self) -> None:
        assert FilterValue().to_wire() == '{"filters": []}'
        assert json.loads(FilterValue().to_wire()) == {"filters": []}

    def test_clause_emits_authoritative_basefilter_keys(self) -> None:
        clause = FilterTermClause(
            field="Sample type",
            type="string",
            is_range=False,
            value=["culture", "blood"],
        )

        assert json.loads(FilterValue(filters=[clause]).to_wire()) == {
            "filters": [
                {
                    "field": "Sample type",
                    "type": "string",
                    "isRange": False,
                    "includeUnknown": False,
                    "value": ["culture", "blood"],
                }
            ]
        }

    def test_parse_drops_noise_keys_keeps_canonical(self) -> None:
        raw = {
            "filters": [
                {
                    "field": "Country",
                    "type": "string",
                    "isRange": False,
                    "includeUnknown": True,
                    "value": ["India"],
                    "fieldDisplayName": "Country",
                }
            ]
        }

        parsed = param_value_from_raw(raw, "filter")

        assert parsed == FilterValue(
            filters=[
                FilterTermClause(
                    field="Country",
                    type="string",
                    is_range=False,
                    include_unknown=True,
                    value=["India"],
                )
            ]
        )
        assert "fieldDisplayName" not in json.loads(parsed.to_wire())["filters"][0]
