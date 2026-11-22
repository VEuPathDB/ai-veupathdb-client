from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from veupathdb.domain.parameters import (
    FilterValue,
    HeldValue,
    MultiPickValue,
    NumberValue,
    ParamValue,
    SinglePickValue,
    StringValue,
    from_wire,
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
