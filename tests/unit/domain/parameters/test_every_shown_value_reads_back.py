from __future__ import annotations

from datetime import date

from hypothesis import given
from hypothesis import strategies as st
from pydantic import JsonValue, TypeAdapter

from veupathdb.domain.parameters import (
    FilterFacets,
    FilterProposals,
    FilterValue,
    HeldValue,
    ParamValue,
    from_wire,
    restates,
    shown_stated,
    stated_form,
)
from veupathdb.domain.parameters.values import (
    DateRangeValue,
    DateValue,
    InputDatasetValue,
    InputStepValue,
    MultiPickValue,
    NumberRangeValue,
    NumberValue,
    SinglePickValue,
    StringValue,
    TimestampValue,
)
from veupathdb.wdk.wdk_parameters import WDKParameter

_PARAM: TypeAdapter[WDKParameter] = TypeAdapter(WDKParameter)
_VALUE: TypeAdapter[ParamValue] = TypeAdapter(ParamValue)

_TERMS = ["a", "b", "c"]
_VOCABULARY: JsonValue = [[t, t.upper(), None] for t in _TERMS]
_LEAVES = ["a1", "a2", "b1"]
_TREE: JsonValue = {
    "data": {"term": "@@fake@@", "display": "@@fake@@"},
    "children": [
        {
            "data": {"term": "a", "display": "A"},
            "children": [
                {"data": {"term": "a1", "display": "A one"}, "children": []},
                {"data": {"term": "a2", "display": "A two"}, "children": []},
            ],
        },
        {
            "data": {"term": "b", "display": "B"},
            "children": [{"data": {"term": "b1", "display": "B one"}, "children": []}],
        },
    ],
}
_SEXES = ["female", "male"]
_COUNTS = ["1", "2", "3"]
_FACETS: JsonValue = [
    {"term": "sex", "display": "Sex", "type": "string"},
    {"term": "age", "display": "Age", "type": "number", "isRange": True},
    {"term": "count", "display": "Count", "type": "number"},
    {"term": "collected", "display": "Collected", "type": "date", "isRange": True},
    {"term": "group", "display": "Group", "type": "multiFilter"},
]


def _declared(kind: str, **more: JsonValue) -> WDKParameter:
    return _PARAM.validate_python({"name": "p", "type": kind, **more})


_DAY = st.dates(min_value=date(1900, 1, 1), max_value=date(2100, 12, 31)).map(
    date.isoformat
)
_BOUND = st.floats(min_value=0, max_value=100).map(lambda v: round(v, 3))


def _clause(field: str, kind: str, ranged: bool, value: JsonValue) -> JsonValue:
    return {
        "field": field,
        "type": kind,
        "isRange": ranged,
        "includeUnknown": False,
        "value": value,
    }


def _span[T: (float, str)](
    bound: st.SearchStrategy[T],
) -> st.SearchStrategy[dict[str, T]]:
    return st.tuples(bound, bound).map(
        lambda pair: {"min": min(pair), "max": max(pair)}
    )


def _members(field: str, members: list[str]) -> st.SearchStrategy[JsonValue]:
    return st.lists(st.sampled_from(members), min_size=1, unique=True).map(
        lambda v: _clause(field, "string", False, list(v))
    )


_CLAUSES: st.SearchStrategy[list[JsonValue]] = st.lists(
    st.one_of(
        _members("sex", _SEXES),
        _span(_BOUND).map(lambda v: _clause("age", "number", True, dict(v))),
        st.lists(st.sampled_from(_COUNTS), min_size=1, unique=True).map(
            lambda v: _clause("count", "number", False, [int(n) for n in v])
        ),
        _span(_DAY).map(lambda v: _clause("collected", "date", True, dict(v))),
    ),
    max_size=3,
)
_CLAUSE_FILTERS: st.SearchStrategy[ParamValue] = _CLAUSES.map(
    lambda clauses: FilterValue.model_validate({"filters": clauses})
)
_FILTERS: st.SearchStrategy[ParamValue] = st.one_of(
    st.just(FilterValue(empty=True)), _CLAUSE_FILTERS
)
_FILTER_VALUES: JsonValue = {"sex": list(_SEXES), "count": list(_COUNTS)}


def _picks(terms: list[str], fewest: int) -> st.SearchStrategy[ParamValue]:
    return st.lists(st.sampled_from(terms), min_size=fewest, unique=True).map(
        lambda v: MultiPickValue(values=v)
    )


_TEXT = st.text(min_size=1)

_CASES: dict[str, tuple[WDKParameter, st.SearchStrategy[ParamValue]]] = {
    "string": (
        _declared("string"),
        _TEXT.map(lambda v: StringValue(value=v)),
    ),
    "number-text": (
        _declared("string", isNumber=True),
        st.from_regex(r"[+-]?[0-9]+(\.[0-9]+)?", fullmatch=True).map(
            lambda v: StringValue(value=v)
        ),
    ),
    "number": (
        _declared("number", min=0, max=100, allowEmptyValue=True),
        st.one_of(st.none(), _BOUND).map(lambda v: NumberValue(value=v)),
    ),
    "required-number": (
        _declared("number", min=0, max=100),
        _BOUND.map(lambda v: NumberValue(value=v)),
    ),
    "number-range": (
        _declared("number-range", min=0, max=100),
        _span(_BOUND).map(NumberRangeValue.model_validate),
    ),
    "date": (_declared("date"), _DAY.map(lambda v: DateValue(value=v))),
    "date-range": (
        _declared("date-range"),
        _span(_DAY).map(DateRangeValue.model_validate),
    ),
    "timestamp": (
        _declared("timestamp"),
        _TEXT.map(lambda v: TimestampValue(value=v)),
    ),
    "single-pick-vocabulary": (
        _declared("single-pick-vocabulary", vocabulary=_VOCABULARY),
        st.sampled_from(_TERMS).map(lambda v: SinglePickValue(value=v)),
    ),
    "tree-single-pick": (
        _declared("single-pick-vocabulary", vocabulary=_TREE, displayType="treeBox"),
        st.sampled_from(_LEAVES).map(lambda v: SinglePickValue(value=v)),
    ),
    "multi-pick-vocabulary": (
        _declared(
            "multi-pick-vocabulary", vocabulary=_VOCABULARY, allowEmptyValue=True
        ),
        _picks(_TERMS, 0),
    ),
    "required-multi-pick": (
        _declared("multi-pick-vocabulary", vocabulary=_VOCABULARY),
        _picks(_TERMS, 1),
    ),
    "tree-multi-pick": (
        _declared("multi-pick-vocabulary", vocabulary=_TREE, displayType="treeBox"),
        _picks(_LEAVES, 1),
    ),
    "filter": (
        _declared(
            "filter", ontology=_FACETS, values=_FILTER_VALUES, allowEmptyValue=True
        ),
        _FILTERS,
    ),
    "required-filter": (
        _declared("filter", ontology=_FACETS, values=_FILTER_VALUES),
        _CLAUSE_FILTERS,
    ),
    "input-dataset": (
        _declared("input-dataset"),
        st.integers(min_value=1).map(lambda v: InputDatasetValue(dataset_id=str(v))),
    ),
    "input-step": (
        _declared("input-step"),
        st.integers(min_value=0).map(lambda v: InputStepValue(step_id=str(v))),
    ),
}

_KINDS = st.sampled_from(sorted(_CASES)).flatmap(
    lambda kind: st.tuples(st.just(_CASES[kind][0]), _CASES[kind][1])
)


def _read_wire(param: WDKParameter, stated: JsonValue) -> str:
    match param.read_stated(stated):
        case FilterProposals() as proposals:
            return FilterFacets.of(param).bind(proposals).to_wire()
        case read:
            return _VALUE.validate_python(read).to_wire()


@given(_KINDS)
def test_every_shown_value_reads_back_to_its_wire(
    case: tuple[WDKParameter, ParamValue],
) -> None:
    param, value = case

    assert stated_form(value) == shown_stated(value)
    assert _read_wire(param, shown_stated(value)) == value.to_wire()


@given(st.text())
def test_a_held_value_restated_as_shown_is_kept(wire: str) -> None:
    held = HeldValue(wire=wire)

    assert restates(held, shown_stated(held))
    assert restates(held, wire)


def test_a_multi_filter_restated_as_shown_is_kept() -> None:
    wire = (
        '{"filters": [{"field": "group", "type": "multiFilter", "isRange": false, '
        '"includeUnknown": false, "value": {"operation": "union", "filters": '
        '[{"field": "sex", "type": "string", "isRange": false, '
        '"includeUnknown": false, "value": ["female"]}]}}]}'
    )
    value = from_wire("filter", wire)

    assert restates(value, shown_stated(value))


@given(_KINDS)
def test_a_value_given_back_in_its_stated_form_restates_it(
    case: tuple[WDKParameter, ParamValue],
) -> None:
    _, value = case

    assert restates(value, shown_stated(value))


def test_another_value_is_not_a_restatement() -> None:
    assert not restates(HeldValue(wire="x,y"), "x")
    assert not restates(MultiPickValue(values=["a"]), ["b"])
    assert not restates(FilterValue(), [{"field": "sex", "value": ["female"]}])
