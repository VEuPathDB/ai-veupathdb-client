from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    FilterValue,
    HeldValue,
    MultiPickValue,
    NumberValue,
    ParamValue,
    SinglePickValue,
    StringValue,
    from_wire,
    param_value_key,
    same_as_wire,
    same_param_value,
    same_value,
    to_wire,
)

_TERMS = st.lists(st.sampled_from(["a", "b", "c", "d"]), min_size=1, max_size=4)


def _clause(field: str, members: list[str]) -> dict[str, object]:
    return {
        "field": field,
        "type": "string",
        "isRange": False,
        "includeUnknown": False,
        "value": members,
    }


@given(_TERMS.flatmap(lambda terms: st.tuples(st.just(terms), st.permutations(terms))))
def test_a_multi_pick_is_the_same_value_in_any_order_or_repetition(
    case: tuple[list[str], list[str]],
) -> None:
    terms, shuffled = case

    assert same_value(MultiPickValue(values=terms), MultiPickValue(values=shuffled))
    assert same_value(
        MultiPickValue(values=terms), MultiPickValue(values=[*shuffled, terms[0]])
    )


@given(_TERMS, _TERMS)
def test_two_multi_picks_are_the_same_value_only_with_the_same_terms(
    left: list[str], right: list[str]
) -> None:
    assert same_value(MultiPickValue(values=left), MultiPickValue(values=right)) is (
        set(left) == set(right)
    )


@given(st.permutations([_clause("sex", ["female", "male"]), _clause("age", ["1"])]))
def test_a_filter_is_the_same_value_in_any_clause_order(
    clauses: list[dict[str, object]],
) -> None:
    held = FilterValue.model_validate(
        {"filters": [_clause("sex", ["male", "female"]), _clause("age", ["1"])]}
    )

    assert same_value(held, FilterValue.model_validate({"filters": clauses}))


_VALUES: list[ParamValue] = [
    StringValue(value="kinase"),
    NumberValue(value=5),
    SinglePickValue(value="a"),
    MultiPickValue(values=["b", "a"]),
    FilterValue(),
    FilterValue(empty=True),
    HeldValue(wire="x,y"),
]


@given(st.sampled_from(_VALUES))
def test_a_value_is_the_same_value_as_itself_read_back_from_its_wire(
    value: ParamValue,
) -> None:
    match value:
        case HeldValue():
            read: ParamValue = HeldValue(wire=to_wire(value))
        case _:
            read = from_wire(value.type, to_wire(value))

    assert same_value(value, read)
    assert same_value(read, value)


@given(st.sampled_from(_VALUES), st.sampled_from(_VALUES))
def test_values_of_different_meaning_are_not_the_same(
    left: ParamValue, right: ParamValue
) -> None:
    assert same_value(left, right) is (_VALUES.index(left) == _VALUES.index(right))


_GROUPED = "(pfal>=1T AND pviv>=1T)"
_WRITTEN = "pfal>=1T AND pviv>=1T"


def test_an_expression_parameter_is_the_same_value_in_either_writing() -> None:
    left, right = StringValue(value=_GROUPED), StringValue(value=_WRITTEN)

    assert same_param_value(PHYLETIC_EXPRESSION_PARAM, left, right)
    assert not same_param_value("text_expression", left, right)
    assert param_value_key(PHYLETIC_EXPRESSION_PARAM, left) == param_value_key(
        PHYLETIC_EXPRESSION_PARAM, right
    )


@given(_TERMS.flatmap(lambda terms: st.tuples(st.just(terms), st.permutations(terms))))
def test_a_wire_in_another_order_or_spacing_is_the_held_value(
    case: tuple[list[str], list[str]],
) -> None:
    terms, shuffled = case
    held = MultiPickValue(values=terms)

    assert same_as_wire("organism", held, json.dumps(shuffled, separators=(",", ":")))
    assert param_value_key("organism", held) == param_value_key(
        "organism", MultiPickValue(values=shuffled)
    )


def test_a_spaced_no_filter_wire_is_the_held_no_filter() -> None:
    assert same_as_wire("variation_sample_meta", FilterValue(), '{"filters": []}')
    assert not same_as_wire("variation_sample_meta", FilterValue(), "")


def test_a_wire_its_kind_cannot_read_is_another_value() -> None:
    assert not same_as_wire("organism", MultiPickValue(values=["a"]), "{not json")
    assert not same_as_wire("variation_sample_meta", FilterValue(), "[]")


@pytest.mark.parametrize(("wire", "term"), [('["Pf"]', "Pf"), ("Pf", "Pf"), ("[]", "")])
def test_a_single_pick_reads_its_internal_and_external_stable_value_alike(
    wire: str, term: str
) -> None:
    assert from_wire("single-pick-vocabulary", wire) == SinglePickValue(value=term)


_REGROUPED = ("pfal=0 AND tgon>=1 OR pfal>=1", "pfal=0 AND (tgon>=1 OR pfal>=1)")


def test_parentheses_that_regroup_terms_are_another_expression() -> None:
    left, right = (StringValue(value=text) for text in _REGROUPED)

    assert not same_param_value(PHYLETIC_EXPRESSION_PARAM, left, right)


@pytest.mark.parametrize("name", [PHYLETIC_EXPRESSION_PARAM, "text_expression"])
def test_a_writing_that_does_not_parse_equals_only_itself(name: str) -> None:
    unparsed = StringValue(value="pfal=0 AND")

    assert same_param_value(name, unparsed, unparsed)
    assert not same_param_value(name, unparsed, StringValue(value="pfal=0 OR"))


def test_a_value_of_another_kind_is_read_in_the_held_kind() -> None:
    assert same_param_value("floor", NumberValue(value=1), StringValue(value="1"))
    assert same_param_value("floor", StringValue(value="1.0"), NumberValue(value=1))
    assert same_param_value("floor", NumberValue(value=1), StringValue(value="1.0"))
    assert not same_param_value("floor", NumberValue(value=1), StringValue(value="2"))
    assert not same_param_value("floor", NumberValue(value=1), StringValue(value="one"))
