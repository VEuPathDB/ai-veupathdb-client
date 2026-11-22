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
    ParamKind,
    ParamValue,
    SinglePickValue,
    StringValue,
    changed_param_names,
    from_wire,
    param_value_key,
    same_as_wire,
    same_param_value,
    same_param_values,
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

    assert same_param_value(PHYLETIC_EXPRESSION_PARAM, "string", left, right)
    assert not same_param_value("text_expression", "string", left, right)


@given(_TERMS.flatmap(lambda terms: st.tuples(st.just(terms), st.permutations(terms))))
def test_a_wire_in_another_order_or_spacing_is_the_held_value(
    case: tuple[list[str], list[str]],
) -> None:
    terms, shuffled = case
    held = MultiPickValue(values=terms)

    assert same_as_wire("organism", held, json.dumps(shuffled, separators=(",", ":")))


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

    assert not same_param_value(PHYLETIC_EXPRESSION_PARAM, "string", left, right)


@pytest.mark.parametrize("name", [PHYLETIC_EXPRESSION_PARAM, "text_expression"])
def test_a_writing_that_does_not_parse_equals_only_itself(name: str) -> None:
    unparsed = StringValue(value="pfal=0 AND")

    assert same_param_value(name, "string", unparsed, unparsed)
    assert not same_param_value(
        name, "string", unparsed, StringValue(value="pfal=0 OR")
    )


def test_a_number_parameter_reads_every_spelling_of_one_number_alike() -> None:
    assert same_param_value(
        "floor", "number", StringValue(value="1.0"), NumberValue(value=1)
    )
    assert same_param_value(
        "floor", "number", StringValue(value="1.0"), StringValue(value="1")
    )
    assert not same_param_value(
        "floor", "number", NumberValue(value=1), StringValue(value="2")
    )
    assert not same_param_value(
        "floor", "number", NumberValue(value=1), StringValue(value="one")
    )


def test_a_string_parameter_holds_two_spellings_of_one_number_apart() -> None:
    assert not same_param_value(
        "text", "string", StringValue(value="1.0"), StringValue(value="1")
    )
    assert not same_param_value(
        "text", "string", StringValue(value="1.0"), NumberValue(value=1)
    )
    assert same_param_value(
        "text", "string", StringValue(value="1"), NumberValue(value=1)
    )


def test_without_a_declared_kind_each_value_keeps_its_own() -> None:
    assert not same_param_value(
        "floor", None, StringValue(value="1"), NumberValue(value=1)
    )
    assert not same_param_value(
        "organism", None, HeldValue(wire='["a"]'), MultiPickValue(values=["a"])
    )
    assert same_param_value(
        "organism",
        None,
        MultiPickValue(values=["b", "a"]),
        MultiPickValue(values=["a", "b"]),
    )


_KEYED: list[tuple[ParamKind, ParamValue, ParamValue]] = [
    (
        "multi-pick-vocabulary",
        HeldValue(wire='["b","a"]'),
        MultiPickValue(values=["a", "b"]),
    ),
    ("filter", FilterValue(), HeldValue(wire='{"filters": []}')),
    ("single-pick-vocabulary", SinglePickValue(value="a"), HeldValue(wire='["a"]')),
    ("number", NumberValue(value=1), StringValue(value="1.0")),
    ("number", NumberValue(value=1), HeldValue(wire="1e0")),
]


@pytest.mark.parametrize(("kind", "left", "right"), _KEYED)
def test_one_value_has_one_key(
    kind: ParamKind, left: ParamValue, right: ParamValue
) -> None:
    assert same_param_value("p", kind, left, right)
    assert param_value_key("p", kind, left) == param_value_key("p", kind, right)


_KINDS: list[ParamKind] = [
    "string",
    "number",
    "single-pick-vocabulary",
    "multi-pick-vocabulary",
    "filter",
]
_WIRES = st.sampled_from(
    [
        "1",
        "1.0",
        "1e0",
        "2",
        "a",
        '["a"]',
        '["a","b"]',
        '["b", "a"]',
        "[]",
        '{"filters":[]}',
        '{"filters": []}',
        "",
        "{not json",
    ]
)
_ANY_VALUE = st.one_of(
    _WIRES.map(lambda wire: HeldValue(wire=wire)),
    _WIRES.map(lambda wire: StringValue(value=wire)),
    st.sampled_from(
        [NumberValue(value=1), NumberValue(value=2), NumberValue(value=None)]
    ),
    st.sampled_from(["a", "b", ""]).map(lambda term: SinglePickValue(value=term)),
    _TERMS.map(lambda terms: MultiPickValue(values=terms)),
    st.sampled_from([FilterValue(), FilterValue(empty=True)]),
)


@given(st.sampled_from(_KINDS), _ANY_VALUE, _ANY_VALUE, _ANY_VALUE)
def test_one_kind_reads_values_as_an_equivalence(
    kind: ParamKind, a: ParamValue, b: ParamValue, c: ParamValue
) -> None:
    assert same_param_value("p", kind, a, a)
    assert same_param_value("p", kind, a, b) is same_param_value("p", kind, b, a)
    if same_param_value("p", kind, a, b) and same_param_value("p", kind, b, c):
        assert same_param_value("p", kind, a, c)


@given(st.sampled_from([*_KINDS, None]), _ANY_VALUE, _ANY_VALUE)
def test_equal_values_have_equal_keys(
    kind: ParamKind | None, a: ParamValue, b: ParamValue
) -> None:
    assert same_param_value("p", kind, a, b) is (
        param_value_key("p", kind, a) == param_value_key("p", kind, b)
    )


def test_two_maps_differ_by_the_names_whose_values_differ() -> None:
    before: dict[str, ParamValue] = {
        "organism": MultiPickValue(values=["a", "b"]),
        "floor": NumberValue(value=1),
    }
    after: dict[str, ParamValue] = {
        "organism": MultiPickValue(values=["b", "a"]),
        "floor": NumberValue(value=2),
    }

    assert changed_param_names(before, after) == ["floor"]
    assert not same_param_values(before, after)
    assert same_param_values(before, {**after, "floor": NumberValue(value=1)})
    assert changed_param_names(before, {"floor": NumberValue(value=1)}) == ["organism"]
