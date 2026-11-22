from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter

from veupathdb.domain.parameters import (
    HeldValue,
    MultiPickValue,
    ParameterCanonicalizer,
    ParamValue,
    SinglePickValue,
    StatedValuesError,
    StringValue,
    fill_site_set_defaults,
    from_wire_as,
    held_names,
    value_kind,
    wire_map,
)
from veupathdb.domain.parameters.specs import ParamSpecNormalized
from veupathdb.domain.parameters.stated import stated_reading
from veupathdb.domain.parameters.values import NumberRangeValue
from veupathdb.domain.parameters.wdk_vocab import WDKVocabTerm
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse
from veupathdb.wdk.wdk_parameters import (
    WDKAnswerParam,
    WDKDatasetParam,
    WDKDateParam,
    WDKDateRangeParam,
    WDKEnumParam,
    WDKFilterParam,
    WDKNumberParam,
    WDKNumberRangeParam,
    WDKParameter,
    WDKStringParam,
    WDKTimestampParam,
)

_WEIGHT = "wdk/search_genes_by_molecular_weight.json"


def _organism() -> ParamSpecNormalized:
    search = WDKSearchResponse.model_validate(
        load_recorded("search_genes_by_molecular_weight").json_body()
    ).search_data
    param = next(p for p in search.parameters or [] if p.name == "organism")
    return ParamSpecNormalized(
        name=param.name,
        param_type=param.type,
        vocabulary=param.vocabulary,
        count_only_leaves=True,
    )


@pytest.mark.skipif(needs_qa_recording(_WEIGHT), reason=NEEDS_QA_RECORDING)
def test_a_branch_wdk_holds_is_read_without_expanding_to_leaves() -> None:
    spec = _organism()
    wire = json.dumps(["Haemoproteidae"])

    held = ParameterCanonicalizer({"organism": spec}).held({"organism": wire})

    assert held == {"organism": MultiPickValue(values=["Haemoproteidae"])}
    assert ParameterCanonicalizer({"organism": spec}).canonicalize(held) == {
        "organism": MultiPickValue(values=["Haemoproteus tartakovskyi strain SISKIN1"])
    }


def test_an_open_range_wdk_holds_stays_open() -> None:
    spec = ParamSpecNormalized(name="r", param_type="number-range", min=0, max=10)

    held = ParameterCanonicalizer({"r": spec}).held({"r": '{"min": 2}'})

    assert held == {"r": NumberRangeValue(min=2)}


def test_a_term_wdk_holds_is_not_matched_to_another_spelling() -> None:
    spec = ParamSpecNormalized(
        name="p",
        param_type="single-pick-vocabulary",
        vocabulary=[WDKVocabTerm(("Yes", "yes", None))],
    )

    held = ParameterCanonicalizer({"p": spec}).held({"p": "YES"})

    assert held == {"p": SinglePickValue(value="YES")}


def test_a_name_with_no_spec_is_held_as_wdk_holds_it() -> None:
    held = ParameterCanonicalizer({}).held({"retired": "a, b"})

    assert held == {"retired": HeldValue(wire="a, b")}


def test_a_declared_input_step_is_the_wiring_and_not_a_value() -> None:
    spec = ParamSpecNormalized(name="gene_result", param_type="input-step")

    held = ParameterCanonicalizer({"gene_result": spec}).held(
        {"gene_result": "10", "retired": "10"}
    )

    assert held == {"retired": HeldValue(wire="10")}


def test_a_held_value_goes_out_byte_identical() -> None:
    wire = {"a": "not, json", "b": '{"min":1 }', "c": ""}

    held = ParameterCanonicalizer({}).held(wire)

    assert wire_map(held) == wire


def test_the_write_entry_passes_a_held_value_through_untouched() -> None:
    spec = ParamSpecNormalized(name="n", param_type="number")
    values: dict[str, ParamValue] = {
        "n": HeldValue(wire="abc"),
        "retired": HeldValue(wire="x"),
    }

    assert ParameterCanonicalizer({"n": spec}).canonicalize(values) == values


def test_a_held_value_round_trips_through_the_union() -> None:
    adapter: TypeAdapter[ParamValue] = TypeAdapter(ParamValue)

    dumped = adapter.dump_python(HeldValue(wire="abc"), by_alias=True, mode="json")

    assert dumped == {"type": "held", "wire": "abc"}
    assert adapter.validate_python(dumped) == HeldValue(wire="abc")


_EVERY_KIND: list[WDKParameter] = [
    WDKStringParam(name="s"),
    WDKNumberParam(name="n", min=0, max=10),
    WDKNumberRangeParam(name="nr", min=0, max=10),
    WDKDateParam(name="d"),
    WDKDateRangeParam(name="dr"),
    WDKTimestampParam(name="t"),
    WDKEnumParam(
        name="sp",
        type="single-pick-vocabulary",
        vocabulary=[WDKVocabTerm(("a", "a", None))],
    ),
    WDKEnumParam(
        name="mp",
        type="multi-pick-vocabulary",
        vocabulary=[WDKVocabTerm(("a", "a", None))],
    ),
    WDKFilterParam(name="f"),
    WDKDatasetParam(name="ds"),
    WDKAnswerParam(name="st"),
]


@pytest.mark.parametrize("param", _EVERY_KIND, ids=lambda p: p.type)
def test_no_stated_value_is_read_as_held(param: WDKParameter) -> None:
    reading = stated_reading(param)

    with pytest.raises(StatedValuesError):
        reading.read({"type": "held", "wire": "a"})
    assert '"held"' not in json.dumps(reading.adapter.json_schema())


def test_a_held_value_has_no_kind_and_reads_another_wire_as_held() -> None:
    held = HeldValue(wire="abc")

    assert (value_kind(held), from_wire_as(held, "x")) == (None, HeldValue(wire="x"))
    assert from_wire_as(NumberRangeValue(), '{"min": 1}') == NumberRangeValue(min=1)


def test_a_site_set_default_never_fills_over_a_held_value() -> None:
    spec = ParamSpecNormalized(
        name="hidden",
        param_type="string",
        is_visible=False,
        initial_display_value="site",
    )
    held: dict[str, ParamValue] = {"hidden": HeldValue(wire="kept")}

    assert fill_site_set_defaults({"hidden": spec}, held) == held
    assert fill_site_set_defaults({"hidden": spec}, {}) == {
        "hidden": StringValue(value="site")
    }


def test_the_held_names_are_the_values_no_kind_reads() -> None:
    values: dict[str, ParamValue] = {
        "a": HeldValue(wire="x"),
        "b": NumberRangeValue(min=1),
    }

    assert held_names(values) == frozenset({"a"})
