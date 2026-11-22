from __future__ import annotations

import datetime
import json
from collections.abc import Callable, Hashable
from decimal import Decimal
from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st

from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    FilterValue,
    HeldValue,
    InputDatasetValue,
    InputStepValue,
    MultiPickValue,
    NumberValue,
    ParamKind,
    ParamValue,
    SinglePickValue,
    StringValue,
    as_param_kind,
    from_wire,
    same_param_value,
)
from veupathdb.domain.parameters.values import (
    DateRangeValue,
    DateValue,
    NumberRangeValue,
    TimestampValue,
)

_TERMS = st.lists(st.sampled_from(["a", "b", "c"]), max_size=4)
_TEXT = st.sampled_from(["", "a", "b", "1", "1.0"])
_NUMBERS = st.sampled_from([None, 0.0, 1.0, 1.5, 2.0])
_DAYS = st.sampled_from([None, "2024-01-01", "2024-01-02"])
_DIGITS = st.sampled_from(["", "1", "2", "12"])
_CLAUSES = st.none() | st.lists(
    st.tuples(
        st.sampled_from(["sex", "age"]),
        st.lists(st.sampled_from(["x", "y"]), min_size=1, max_size=2),
    ),
    max_size=2,
)

type _Clauses = list[tuple[str, list[str]]] | None
type _Case = tuple[ParamValue, Hashable]


def _decimal(number: float | None) -> Decimal | None:
    return None if number is None else Decimal(number)


def _day(text: str | None) -> datetime.date | None:
    return None if text is None else datetime.date.fromisoformat(text)


def _clause(field: str, members: list[str]) -> dict[str, object]:
    return {
        "field": field,
        "type": "string",
        "isRange": False,
        "includeUnknown": False,
        "value": members,
    }


def _filter(clauses: _Clauses) -> ParamValue:
    if clauses is None:
        return FilterValue(empty=True)
    return FilterValue.model_validate(
        {"filters": [_clause(field, members) for field, members in clauses]}
    )


def _filter_oracle(clauses: _Clauses) -> Hashable:
    if clauses is None:
        return None
    return frozenset((field, frozenset(members)) for field, members in clauses)


def _ordered(
    pair: tuple[float | None, float | None],
) -> tuple[float | None, float | None]:
    low, high = pair
    if low is not None and high is not None and low > high:
        return high, low
    return low, high


def _ranged(pair: tuple[float | None, float | None]) -> ParamValue:
    low, high = _ordered(pair)
    return NumberRangeValue(min=low, max=high)


def _range_oracle(pair: tuple[float | None, float | None]) -> Hashable:
    low, high = _ordered(pair)
    return (_decimal(low), _decimal(high))


def _dated(pair: tuple[str | None, str | None]) -> ParamValue:
    return DateRangeValue(min=pair[0], max=pair[1])


def _kind[T](
    raw: st.SearchStrategy[T],
    build: Callable[[T], ParamValue],
    oracle: Callable[[T], Hashable],
) -> st.SearchStrategy[_Case]:
    return raw.map(lambda r: (build(r), oracle(r)))


_KINDS: dict[ParamKind, st.SearchStrategy[_Case]] = {
    "string": _kind(_TEXT, lambda t: StringValue(value=t), lambda t: t),
    "number": _kind(_NUMBERS, lambda n: NumberValue(value=n), _decimal),
    "number-range": _kind(st.tuples(_NUMBERS, _NUMBERS), _ranged, _range_oracle),
    "date": _kind(_DAYS, lambda d: DateValue(value=d), _day),
    "date-range": _kind(
        st.tuples(_DAYS, _DAYS), _dated, lambda pair: (_day(pair[0]), _day(pair[1]))
    ),
    "timestamp": _kind(_TEXT, lambda t: TimestampValue(value=t), lambda t: t),
    "single-pick-vocabulary": _kind(
        _TEXT, lambda t: SinglePickValue(value=t), lambda t: t
    ),
    "multi-pick-vocabulary": _kind(
        _TERMS, lambda terms: MultiPickValue(values=terms), frozenset
    ),
    "filter": _kind(_CLAUSES, _filter, _filter_oracle),
    "input-dataset": _kind(
        _DIGITS, lambda d: InputDatasetValue(dataset_id=d), lambda d: d
    ),
    "input-step": _kind(_DIGITS, lambda d: InputStepValue(step_id=d), lambda d: d),
}

_ONE_KIND = st.sampled_from(sorted(_KINDS)).flatmap(
    lambda kind: st.tuples(_KINDS[kind], _KINDS[kind])
)
_ANY = st.one_of(*_KINDS.values())


def test_every_kind_is_drawn() -> None:
    assert sorted(_KINDS) == sorted(get_args(ParamKind))


@given(_ONE_KIND)
def test_two_values_of_one_kind_are_equal_exactly_when_their_meaning_is(
    pair: tuple[_Case, _Case],
) -> None:
    (left, meant_left), (right, meant_right) = pair

    assert (left == right, left != right) == (
        meant_left == meant_right,
        meant_left != meant_right,
    )
    if left == right:
        assert hash(left) == hash(right)


@given(_ANY, _ANY)
def test_values_of_two_kinds_are_never_equal(left: _Case, right: _Case) -> None:
    (value, _), (other, _) = left, right

    if value.type != other.type:
        assert (value == other, value != other) == (False, True)


@given(_ANY)
def test_a_value_is_its_own_wire_held(case: _Case) -> None:
    value, _ = case
    held = HeldValue(wire=value.to_wire())

    assert (value == held, held == value) == (True, True)


@given(_ANY)
def test_a_value_is_read_back_from_its_wire(case: _Case) -> None:
    value, _ = case

    assert from_wire(as_param_kind(value.type), value.to_wire()) == value


@pytest.mark.parametrize(
    ("value", "wire"),
    [
        (NumberValue(value=1), "1.0"),
        (NumberValue(value=1), "1e0"),
        (MultiPickValue(values=["a", "b"]), '["b", "a", "a"]'),
        (FilterValue(), '{"filters": []}'),
        (SinglePickValue(value="a"), '["a"]'),
        (NumberRangeValue(min=1, max=2), '{"max": 2.0, "min": 1}'),
    ],
    ids=[
        "decimal",
        "exponent",
        "reordered",
        "spaced-no-filter",
        "one-term-array",
        "range",
    ],
)
def test_a_held_wire_in_another_spelling_is_the_value(
    value: ParamValue, wire: str
) -> None:
    held = HeldValue(wire=wire)

    assert (value == held, held == value) == (True, True)


@pytest.mark.parametrize(
    ("value", "wire"),
    [
        (StringValue(value="1"), "1.0"),
        (MultiPickValue(values=["a"]), "{not json"),
        (FilterValue(), "[]"),
        (FilterValue(), ""),
    ],
    ids=["string-spelling", "unread-pick", "unread-filter", "empty-filter"],
)
def test_a_held_wire_the_kind_reads_otherwise_is_another_value(
    value: ParamValue, wire: str
) -> None:
    assert value != HeldValue(wire=wire)


def test_two_held_values_compare_as_their_wires() -> None:
    assert HeldValue(wire='["a","b"]') == HeldValue(wire='["a","b"]')
    assert HeldValue(wire='["a","b"]') != HeldValue(wire='["b","a"]')


def test_a_held_value_has_no_hash() -> None:
    with pytest.raises(TypeError):
        hash(HeldValue(wire="a"))


def test_a_map_and_a_set_compare_their_values_as_values() -> None:
    left: dict[str, ParamValue] = {"organism": MultiPickValue(values=["a", "b"])}
    right: dict[str, ParamValue] = {"organism": MultiPickValue(values=["b", "a"])}

    assert left == right
    assert MultiPickValue(values=["b", "a"]) in {
        MultiPickValue(values=["a", "b"]),
        MultiPickValue(values=["c"]),
    }


@pytest.mark.parametrize(
    ("kind", "left", "right", "same"),
    [
        ("number", StringValue(value="1.0"), NumberValue(value=1), True),
        ("number", HeldValue(wire="1.0"), HeldValue(wire="1"), True),
        ("string", StringValue(value="1.0"), NumberValue(value=1), False),
        ("string", HeldValue(wire="1.0"), HeldValue(wire="1"), False),
        (
            "multi-pick-vocabulary",
            HeldValue(wire='["a","b"]'),
            HeldValue(wire='["b","a"]'),
            True,
        ),
        (
            "filter",
            HeldValue(wire='{"filters":[]}'),
            HeldValue(wire='{"filters": []}'),
            True,
        ),
        ("number", HeldValue(wire="one"), HeldValue(wire="one"), True),
        ("number", HeldValue(wire="one"), HeldValue(wire="two"), False),
    ],
)
def test_the_declared_kind_reads_both_sides(
    kind: ParamKind, left: ParamValue, right: ParamValue, same: bool
) -> None:
    assert (
        same_param_value("p", kind, left, right),
        same_param_value("p", kind, right, left),
    ) == (same, same)


_GROUPED = "(pfal>=1T AND pviv>=1T)"
_WRITTEN = "pfal>=1T AND pviv>=1T"
_REGROUPED = ("pfal=0 AND tgon>=1 OR pfal>=1", "pfal=0 AND (tgon>=1 OR pfal>=1)")


def test_an_expression_parameter_is_the_same_value_in_either_writing() -> None:
    left, right = StringValue(value=_GROUPED), StringValue(value=_WRITTEN)

    assert same_param_value(PHYLETIC_EXPRESSION_PARAM, "string", left, right)
    assert not same_param_value("text_expression", "string", left, right)
    assert left != right


def test_parentheses_that_regroup_terms_are_another_expression() -> None:
    left, right = (StringValue(value=text) for text in _REGROUPED)

    assert not same_param_value(PHYLETIC_EXPRESSION_PARAM, "string", left, right)


@pytest.mark.parametrize(("wire", "term"), [('["Pf"]', "Pf"), ("Pf", "Pf"), ("[]", "")])
def test_a_single_pick_reads_its_internal_and_external_stable_value_alike(
    wire: str, term: str
) -> None:
    assert from_wire("single-pick-vocabulary", wire) == SinglePickValue(value=term)


def test_a_filter_wire_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(TypeError):
        from_wire("filter", json.dumps([]))
