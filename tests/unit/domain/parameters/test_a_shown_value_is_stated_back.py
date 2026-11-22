from __future__ import annotations

import json

import pytest
from pydantic import JsonValue, TypeAdapter

from veupathdb.domain.parameters import (
    FilterFacets,
    FilterProposals,
    FilterStatementError,
    FilterValue,
    HeldValue,
    KeptValue,
    ParamValue,
    StatedValuesError,
    from_wire,
    shown_stated,
    shown_stated_text,
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
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse
from veupathdb.wdk.wdk_parameters import WDKParameter

_PARAM: TypeAdapter[WDKParameter] = TypeAdapter(WDKParameter)
_VALUE: TypeAdapter[ParamValue] = TypeAdapter(ParamValue)

_FACETS: list[JsonValue] = [
    {"term": "sex", "display": "Sex", "type": "string"},
    {"term": "age", "display": "Age", "type": "number", "isRange": True},
    {"term": "count", "display": "Count", "type": "number"},
    {"term": "collected", "display": "Collected", "type": "date", "isRange": True},
    {"term": "group", "display": "Group", "type": "multiFilter"},
]

_DECLARED: dict[str, JsonValue] = {
    "text": {"name": "text", "type": "string"},
    "cutoff": {"name": "cutoff", "type": "string", "isNumber": True},
    "count": {"name": "count", "type": "number", "min": 0, "max": 100},
    "span": {"name": "span", "type": "number-range", "min": 0, "max": 100},
    "open_span": {"name": "open_span", "type": "number-range"},
    "day": {"name": "day", "type": "date"},
    "days": {"name": "days", "type": "date-range"},
    "stamp": {"name": "stamp", "type": "timestamp"},
    "pick": {
        "name": "pick",
        "type": "single-pick-vocabulary",
        "vocabulary": [["a", "A", None], ["b", "B", None]],
    },
    "picks": {
        "name": "picks",
        "type": "multi-pick-vocabulary",
        "vocabulary": [["a", "A", None], ["b", "B", None]],
    },
    "optional_picks": {
        "name": "optional_picks",
        "type": "multi-pick-vocabulary",
        "allowEmptyValue": True,
        "vocabulary": [["a", "A", None], ["b", "B", None]],
    },
    "optional_count": {
        "name": "optional_count",
        "type": "number",
        "allowEmptyValue": True,
    },
    "samples": {
        "name": "samples",
        "type": "filter",
        "ontology": _FACETS,
        "values": {"sex": ["female", "male"], "count": ["1", "2", "3"]},
    },
    "optional_samples": {
        "name": "optional_samples",
        "type": "filter",
        "allowEmptyValue": True,
        "ontology": _FACETS,
        "values": {"sex": ["female", "male"]},
    },
    "ids": {"name": "ids", "type": "input-dataset"},
    "step": {"name": "step", "type": "input-step"},
}


def _param(name: str) -> WDKParameter:
    return _PARAM.validate_python(_DECLARED[name])


def _read_back(name: str, value: ParamValue) -> str:
    param = _param(name)
    form = stated_form(value)
    assert not isinstance(form, KeptValue)
    read = param.read_stated(form)
    match read:
        case FilterProposals():
            return FilterFacets.of(param).bind(read).to_wire()
        case _:
            return _VALUE.validate_python(read).to_wire()


_STATEABLE: list[tuple[str, ParamValue]] = [
    ("text", StringValue(value="kinase")),
    ("cutoff", StringValue(value="0.5")),
    ("count", NumberValue(value=3)),
    ("count", NumberValue(value=2.5)),
    ("optional_count", NumberValue(value=None)),
    ("span", NumberRangeValue(min=1, max=20)),
    ("day", DateValue(value="2024-03-01")),
    ("days", DateRangeValue(min="2024-01-01", max="2024-02-01")),
    ("stamp", TimestampValue(value="2024-01-01T00:00:00")),
    ("pick", SinglePickValue(value="b")),
    ("picks", MultiPickValue(values=["a", "b"])),
    ("optional_picks", MultiPickValue(values=[])),
    ("ids", InputDatasetValue(dataset_id="123")),
    ("step", InputStepValue(step_id="42")),
    ("optional_samples", from_wire("filter", "")),
]

_HELD_WIRES: list[tuple[str, str]] = [
    (
        "samples",
        '{"filters": [{"field": "sex", "type": "string", "isRange": false, "includeUnknown": false, "value": ["female"]}]}',
    ),
    (
        "samples",
        '{"filters": [{"field": "age", "type": "number", "isRange": true, "includeUnknown": true, "value": {"min": 1.0, "max": 5.0}}]}',
    ),
    (
        "samples",
        '{"filters": [{"field": "age", "type": "number", "isRange": true, "includeUnknown": false, "value": {"min": 1.0}}]}',
    ),
    (
        "samples",
        '{"filters": [{"field": "count", "type": "number", "isRange": false, "includeUnknown": false, "value": [1, 3]}]}',
    ),
    (
        "samples",
        '{"filters": [{"field": "collected", "type": "date", "isRange": true, "includeUnknown": false, "value": {"min": "2020-01-01", "max": "2021-01-01"}}]}',
    ),
    ("span", '{"min": 0.0, "max": 100.0}'),
    ("picks", '["b"]'),
]


@pytest.mark.parametrize(("name", "value"), _STATEABLE)
def test_a_value_reads_back_to_its_own_wire(name: str, value: ParamValue) -> None:
    assert _read_back(name, value) == value.to_wire()


@pytest.mark.parametrize(("name", "wire"), _HELD_WIRES)
def test_a_value_wdk_holds_reads_back_to_its_wire(name: str, wire: str) -> None:
    value = from_wire(_param(name).type, wire)

    assert _read_back(name, value) == value.to_wire()


def test_a_filter_is_stated_as_its_clauses() -> None:
    value = from_wire(
        "filter",
        '{"filters": [{"field": "total_variants", "type": "number", "isRange": true, '
        '"includeUnknown": false, "value": {"min": 1.0}}]}',
    )

    assert stated_form(value) == [{"field": "total_variants", "value": {"min": 1.0}}]


def test_a_pick_is_stated_as_its_terms() -> None:
    value = from_wire("multi-pick-vocabulary", '["Plasmodium falciparum 3D7"]')

    assert stated_form(value) == ["Plasmodium falciparum 3D7"]


def test_a_held_value_is_kept() -> None:
    assert stated_form(HeldValue(wire="x,y")) == KeptValue(wire="x,y")


def test_a_filter_with_no_clause_is_kept() -> None:
    assert stated_form(FilterValue()) == KeptValue(wire='{"filters": []}')


def test_a_multi_filter_clause_is_kept() -> None:
    wire = (
        '{"filters": [{"field": "group", "type": "multiFilter", "isRange": false, '
        '"includeUnknown": false, "value": {"operation": "union", "filters": '
        '[{"field": "sex", "type": "string", "isRange": false, '
        '"includeUnknown": false, "value": ["female"]}]}}]}'
    )

    assert stated_form(from_wire("filter", wire)) == KeptValue(wire=wire)


def test_a_range_is_read_with_both_bounds() -> None:
    read = _param("span").read_stated({"min": 5})

    assert read == NumberRangeValue(min=5, max=100)


def test_a_range_with_no_declared_bound_states_both() -> None:
    with pytest.raises(StatedValuesError):
        _param("open_span").read_stated({"min": 5})


def test_an_empty_filter_list_names_a_non_empty_list() -> None:
    with pytest.raises(StatedValuesError) as refusal:
        _param("samples").read_stated([])

    assert "takes a non-empty list of" in str(refusal.value)


_NGS_SNPS = "search_genes_by_ngs_snps"
_NGS_SNPS_FILE = "wdk/search_genes_by_ngs_snps.json"
_YEAR = "VAR_dc0e1a57"
_ARABIC_FIVE = chr(0x0665)


def _recorded(name: str) -> WDKParameter:
    search = WDKSearchResponse.model_validate(
        load_recorded(_NGS_SNPS).json_body()
    ).search_data
    return next(p for p in search.parameters or [] if p.name == name)


def _year_members() -> WDKParameter:
    param = _recorded("variation_sample_meta")
    ontology = [
        term.model_copy(update={"is_range": False}) if term.term == _YEAR else term
        for term in param.ontology
    ]
    values = {**(param.values or {}), _YEAR: ["2010", "2011", "2012.5"]}
    return param.model_copy(update={"ontology": ontology, "values": values})


def _year_wire(stated: JsonValue) -> str:
    param = _year_members()
    read = param.read_stated([{"field": _YEAR, "value": stated}])
    assert isinstance(read, FilterProposals)
    return FilterFacets.of(param).bind(read).to_wire()


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS_FILE), reason=NEEDS_QA_RECORDING)
class TestNumberMembers:
    def test_numbers_and_their_text_bind_the_same(self) -> None:
        assert _year_wire([2010, 2012.5]) == _year_wire(["2010", "2012.5"])

    def test_a_member_goes_out_as_the_text_wdk_matches(self) -> None:
        assert '"value": [2010, 2012.5]' in _year_wire([2010.0, "2012.50"])

    def test_a_number_no_member_equals_is_refused(self) -> None:
        with pytest.raises(FilterStatementError, match="no member 2013"):
            _year_wire([2013])

    def test_a_held_clause_reads_back_to_its_wire(self) -> None:
        wire = (
            f'{{"filters": [{{"field": "{_YEAR}", "type": "number", "isRange": false, '
            '"includeUnknown": false, "value": [2010, 2012.5]}]}'
        )
        value = from_wire("filter", wire)
        form = stated_form(value)

        assert json.dumps(form) == json.dumps(
            [{"field": _YEAR, "value": [2010, 2012.5]}]
        )
        assert (
            FilterFacets.of(_year_members())
            .bind(FilterProposals.model_validate(form))
            .to_wire()
            == value.to_wire()
        )


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS_FILE), reason=NEEDS_QA_RECORDING)
class TestANumberStringWdkHolds:
    @pytest.mark.parametrize(
        "held", ["1e-5", "2.5E+3", "+3", "5.0", "0.000000000000000000001"]
    )
    def test_a_held_number_text_reads_back_as_written(self, held: str) -> None:
        param = _recorded("dn_ds_ratio_lower")
        form = stated_form(StringValue(value=held))
        assert not isinstance(form, KeptValue)

        assert param.read_stated(form) == StringValue(value=held)

    @pytest.mark.parametrize("text", [".5", "5.", "5,000", "1e", "0x10"])
    def test_a_text_wdk_refuses_is_refused(self, text: str) -> None:
        with pytest.raises(StatedValuesError):
            _recorded("dn_ds_ratio_lower").read_stated(text)

    def test_a_number_goes_out_as_its_shortest_decimal(self) -> None:
        assert _recorded("dn_ds_ratio_lower").read_stated(1e-5) == StringValue(
            value="0.00001"
        )


def _members(values: list[str]) -> WDKParameter:
    param = _year_members()
    return param.model_copy(update={"values": {**(param.values or {}), _YEAR: values}})


def _bound(param: WDKParameter, stated: JsonValue) -> str:
    read = param.read_stated([{"field": _YEAR, "value": stated}])
    assert isinstance(read, FilterProposals)
    return FilterFacets.of(param).bind(read).to_wire()


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS_FILE), reason=NEEDS_QA_RECORDING)
class TestAMemberNoNumberWrites:
    @pytest.mark.parametrize(
        ("member", "stated"),
        [("1.50", 1.5), ("1.50", "1.50"), ("1e3", 1000), ("1e3", "1e3"), ("+3", 3)],
    )
    def test_it_goes_out_as_its_published_text(
        self, member: str, stated: JsonValue
    ) -> None:
        wire = _bound(_members([member, "2"]), [stated, 2])

        assert f'"value": [{json.dumps(member)}, 2]' in wire

    def test_a_held_text_member_reads_back_to_its_wire(self) -> None:
        param = _members(["1.50", "2"])
        wire = _bound(param, [1.5, 2])
        form = stated_form(from_wire("filter", wire))

        assert json.dumps(form) == json.dumps([{"field": _YEAR, "value": ["1.50", 2]}])
        assert (
            _bound(param, [1.5, 2])
            == FilterFacets.of(param)
            .bind(FilterProposals.model_validate(form))
            .to_wire()
        )

    def test_a_text_that_is_no_number_is_no_member(self) -> None:
        with pytest.raises(FilterStatementError, match="no member abc"):
            _bound(_members(["1.50", "2"]), ["abc"])

    def test_a_member_in_other_digits_is_no_number(self) -> None:
        with pytest.raises(FilterStatementError, match="no member 5"):
            _bound(_members([_ARABIC_FIVE, "2"]), [5])

    def test_a_member_whose_text_survives_binds(self) -> None:
        assert '"value": [2, 0.5]' in _bound(_members(["2", "0.5"]), ["2", 0.5])


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS_FILE), reason=NEEDS_QA_RECORDING)
def test_a_number_text_in_other_digits_is_refused() -> None:
    with pytest.raises(StatedValuesError):
        _recorded("dn_ds_ratio_lower").read_stated(_ARABIC_FIVE)


def test_a_kept_value_shows_as_the_marked_text() -> None:
    assert (
        shown_stated(FilterValue()) == "'{\"filters\": []}' (kept as the site holds it)"
    )
    assert (
        shown_stated_text(HeldValue(wire="x,y")) == "'x,y' (kept as the site holds it)"
    )


@pytest.mark.parametrize("value", [value for _, value in _STATEABLE])
def test_a_stateable_value_shows_as_its_stated_form(value: ParamValue) -> None:
    assert shown_stated(value) == stated_form(value)
    assert shown_stated_text(value) == json.dumps(stated_form(value))
