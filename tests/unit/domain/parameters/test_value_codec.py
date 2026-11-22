"""The shapes WDK accepts for a multi-pick and a filter value."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError as PydanticValidationError

from veupathdb.domain.parameters.filter_clause import FilterValue, StringMembers
from veupathdb.domain.parameters.value_codec import _PARAM_VALUE_ADAPTER, from_wire
from veupathdb.domain.parameters.values import (
    MultiPickValue,
)


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
            MultiPickValue.model_validate({"values": [{"nope": 1}]})


class TestTheFilterValue:
    """``BaseFilter`` = {field, type, isRange, includeUnknown, value}; an empty
    filter list is "include all"."""

    def test_empty_filter_is_include_all(self) -> None:
        assert FilterValue().to_wire() == '{"filters":[]}'
        assert json.loads(FilterValue().to_wire()) == {"filters": []}

    def test_clause_emits_authoritative_basefilter_keys(self) -> None:
        clause = StringMembers(
            field="Sample type",
            type="string",
            is_range=False,
            include_unknown=False,
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

        parsed = from_wire("filter", json.dumps(raw))

        assert parsed == FilterValue(
            filters=[
                StringMembers(
                    field="Country",
                    type="string",
                    is_range=False,
                    include_unknown=True,
                    value=["India"],
                )
            ]
        )
        assert "fieldDisplayName" not in json.loads(parsed.to_wire())["filters"][0]
