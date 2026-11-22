from __future__ import annotations

import json
from typing import Any, get_args

import pytest
from pydantic import JsonValue, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from veupathdb.domain.parameters import (
    FilterProposals,
    FilterValue,
    ParameterCanonicalizer,
    StatedValuesError,
    VocabularyEntryError,
    decimal_text,
    fill_site_set_defaults,
    read_stated_values,
)
from veupathdb.domain.parameters.specs import ParamSpecNormalized
from veupathdb.domain.parameters.value_codec import from_wire
from veupathdb.domain.parameters.values import (
    DateRangeValue,
    DateValue,
    HeldValue,
    InputDatasetValue,
    InputStepValue,
    MultiPickValue,
    NumberRangeValue,
    ParamKind,
    ParamValue,
    SinglePickValue,
    StringValue,
    empty_value,
)
from veupathdb.domain.parameters.wdk_vocab import WDKVocabTerm, flatten_vocab
from veupathdb.errors import ValidationError
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse
from veupathdb.wdk.wdk_parameters import (
    WDKAnswerParam,
    WDKDatasetParam,
    WDKDateParam,
    WDKEnumParam,
    WDKNumberParam,
    WDKNumberRangeParam,
    WDKParameter,
    WDKStringParam,
    WDKTimestampParam,
)

_ORTHOLOGS = "wdk/search_genes_by_orthologs.json"
_NGS_SNPS = "wdk/search_genes_by_ngs_snps.json"
_AWSTATS = "wdk/search_metrics_awstats.json"


def _params(fixture: str) -> list[WDKParameter]:
    search = WDKSearchResponse.model_validate(
        load_recorded(fixture).json_body()
    ).search_data
    return list(search.parameters or [])


def _param(fixture: str, name: str) -> WDKParameter:
    return next(p for p in _params(fixture) if p.name == name)


def _wire(param: WDKParameter, raw: JsonValue) -> str:
    return TypeAdapter(ParamValue).validate_python(param.read_stated(raw)).to_wire()


def _refused(param: WDKParameter, raw: JsonValue) -> str:
    with pytest.raises(StatedValuesError) as refusal:
        param.read_stated(raw)
    return str(refusal.value)


@pytest.mark.skipif(needs_qa_recording(_ORTHOLOGS), reason=NEEDS_QA_RECORDING)
class TestAYesNoVocabulary:
    def test_a_boolean_is_refused_with_the_terms(self) -> None:
        param = _param("search_genes_by_orthologs", "isSyntenic")

        assert _refused(param, True).endswith(
            "isSyntenic takes one of 'yes', 'no', for example 'yes'; it read True."
        )

    def test_a_term_reads(self) -> None:
        param = _param("search_genes_by_orthologs", "isSyntenic")

        assert param.read_stated("yes") == SinglePickValue(value="yes")

    def test_the_schema_is_the_enum_of_terms(self) -> None:
        param = _param("search_genes_by_orthologs", "isSyntenic")

        assert param.stated_schema() == {"enum": ["yes", "no"], "type": "string"}


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS), reason=NEEDS_QA_RECORDING)
class TestANumberString:
    @pytest.mark.parametrize(
        ("raw", "wire"),
        [(5.0, "5"), (1e-8, "0.00000001"), ("5.0", "5.0"), (0.25, "0.25")],
    )
    def test_a_number_goes_out_as_its_shortest_decimal(
        self, raw: JsonValue, wire: str
    ) -> None:
        param = _param("search_genes_by_ngs_snps", "MinPercentMinorAlleles")

        assert _wire(param, raw) == wire

    @pytest.mark.parametrize("raw", [float("nan"), float("inf"), True, "5,000"])
    def test_a_value_that_is_not_a_number_is_refused(self, raw: JsonValue) -> None:
        param = _param("search_genes_by_ngs_snps", "MinPercentMinorAlleles")

        assert "MinPercentMinorAlleles takes" in _refused(param, raw)


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS), reason=NEEDS_QA_RECORDING)
@pytest.mark.skipif(needs_qa_recording(_AWSTATS), reason=NEEDS_QA_RECORDING)
class TestASmallMultiPick:
    def test_its_items_are_the_enum_of_terms(self) -> None:
        param = _param("search_metrics_awstats", "projectIdSelect")

        assert param.stated_schema() == {
            "items": {
                "enum": [o.value for o in flatten_vocab(param.vocabulary)],
                "type": "string",
            },
            "minItems": 1,
            "type": "array",
        }

    def test_a_term_outside_the_vocabulary_is_refused(self) -> None:
        param = _param("search_metrics_awstats", "projectIdSelect")

        with pytest.raises(VocabularyEntryError) as refused:
            param.read_stated(["PlasmoDB", "NotADB"])

        assert [(n, r.phrase) for n, r in refused.value.faults] == [
            ("projectIdSelect", "NotADB")
        ]

    def test_terms_read(self) -> None:
        param = _param("search_metrics_awstats", "projectIdSelect")

        assert param.read_stated(["PlasmoDB", "ToxoDB"]) == MultiPickValue(
            values=["PlasmoDB", "ToxoDB"]
        )


def test_a_type_ahead_multi_pick_stays_a_list_of_strings() -> None:
    param = WDKEnumParam(
        name="m",
        type="multi-pick-vocabulary",
        display_type="typeAhead",
        vocabulary=[WDKVocabTerm(("a", "a", None)), WDKVocabTerm(("b", "b", None))],
    )

    assert param.stated_schema() == {
        "items": {"minLength": 1, "type": "string"},
        "minItems": 1,
        "type": "array",
    }


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS), reason=NEEDS_QA_RECORDING)
def test_a_tree_multi_pick_stays_a_list_of_strings() -> None:
    param = _param("search_genes_by_ngs_snps", "organismSinglePick")

    assert param.stated_schema() == {
        "items": {"minLength": 1, "type": "string"},
        "maxItems": 1,
        "minItems": 1,
        "type": "array",
    }


class TestNgsSnpsVocabularies:
    def test_a_small_select_is_an_enum(self) -> None:
        param = _param("search_genes_by_ngs_snps", "ReadFrequencyPercent")

        assert param.stated_schema()["enum"] == ["80%", "60%", "40%", "20%"]

    def test_a_multi_pick_reads_a_list(self) -> None:
        param = _param("search_genes_by_ngs_snps", "organismSinglePick")

        assert param.read_stated(["Plasmodium falciparum 3D7"]) == MultiPickValue(
            values=["Plasmodium falciparum 3D7"]
        )

    def test_a_multi_pick_refuses_a_bare_string(self) -> None:
        param = _param("search_genes_by_ngs_snps", "organismSinglePick")

        assert "organismSinglePick takes" in _refused(
            param, "Plasmodium falciparum 3D7"
        )

    def test_every_fault_of_a_search_is_one_refusal(self) -> None:
        stated: dict[str, JsonValue] = {
            "MinPercentMinorAlleles": "x",
            "ReadFrequencyPercent": 10,
        }

        with pytest.raises(StatedValuesError) as refusal:
            read_stated_values(_params("search_genes_by_ngs_snps"), stated)

        assert len(refusal.value.faults) == 2

    def test_every_name_the_declaration_holds_is_read(self) -> None:
        read = read_stated_values(
            _params("search_genes_by_ngs_snps"),
            {"MinPercentMinorAlleles": 5.0, "ReadFrequencyPercent": "80%"},
        )

        assert {
            name: TypeAdapter(ParamValue).validate_python(value).to_wire()
            for name, value in read.items()
        } == {
            "MinPercentMinorAlleles": "5",
            "ReadFrequencyPercent": "80%",
        }


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS), reason=NEEDS_QA_RECORDING)
class TestAFilter:
    def test_a_list_of_clauses_reads_as_proposals(self) -> None:
        param = _param("search_genes_by_ngs_snps", "variation_sample_meta")
        stated: JsonValue = [{"field": "sex", "value": ["female"]}]

        assert param.read_stated(stated) == FilterProposals.model_validate(stated)

    def test_the_schema_names_each_facet_by_term_and_display(self) -> None:
        param = _param("search_genes_by_ngs_snps", "variation_sample_meta")
        schema: dict[str, Any] = param.stated_schema()

        assert {"VAR_68bb04bd", "sex"} <= set(
            schema["items"]["properties"]["field"]["enum"]
        )

    def test_the_shorthand_is_refused_with_the_clause_form(self) -> None:
        param = _param("search_genes_by_ngs_snps", "variation_sample_meta")

        assert "for example [{'field': '<facet>', 'value': ['<member>']}]" in _refused(
            param, "sex=female"
        )

    def test_an_empty_list_reads_as_no_clause(self) -> None:
        param = _param("search_genes_by_ngs_snps", "variation_sample_meta")

        assert param.read_stated([]) == FilterProposals.model_validate([])


class TestANumber:
    _PARAM = WDKNumberParam(name="n", min=0, max=100)

    def test_a_float_goes_out_without_a_point(self) -> None:
        assert _wire(self._PARAM, 5.0) == "5"

    def test_a_value_above_the_maximum_names_it(self) -> None:
        assert "100" in _refused(self._PARAM, 101)

    def test_a_boolean_is_refused(self) -> None:
        assert "n takes" in _refused(self._PARAM, True)


class TestANumberRange:
    def test_an_open_end_closes_from_the_declared_limit(self) -> None:
        param = WDKNumberRangeParam(name="r", min=0, max=10)

        assert _wire(param, {"min": 2}) == '{"min": 2.0, "max": 10.0}'

    def test_an_end_that_cannot_close_is_refused(self) -> None:
        assert "r takes" in _refused(WDKNumberRangeParam(name="r", min=0), {"min": 2})

    @pytest.mark.parametrize("raw", ["20..28", [2, 8]])
    def test_a_range_is_an_object_only(self, raw: JsonValue) -> None:
        param = WDKNumberRangeParam(name="r", min=0, max=30)

        assert "r takes" in _refused(param, raw)


class TestADate:
    _PARAM = WDKDateParam(name="date")

    def test_an_iso_local_date_reads(self) -> None:
        assert self._PARAM.read_stated("2020-01-01") == DateValue(value="2020-01-01")

    @pytest.mark.parametrize("raw", ["20200101", "2020-W01-1", "2020-02-30"])
    def test_another_form_is_refused(self, raw: str) -> None:
        assert "date takes yyyy-mm-dd" in _refused(self._PARAM, raw)


@pytest.mark.skipif(needs_qa_recording(_AWSTATS), reason=NEEDS_QA_RECORDING)
class TestARecordedDateRange:
    def test_a_bound_inside_the_declared_dates_reads(self) -> None:
        param = _param("search_metrics_awstats", "date")

        assert param.read_stated({"min": "2025-01-01"}) == DateRangeValue(
            min="2025-01-01", max="2028-12-31"
        )

    @pytest.mark.parametrize("raw", ["20250101", "2025-W01-1", "2025-02-30"])
    def test_a_bound_in_another_form_is_refused(self, raw: str) -> None:
        param = _param("search_metrics_awstats", "date")

        assert "yyyy-mm-dd" in _refused(param, {"min": raw})

    def test_a_bound_before_the_declared_dates_is_refused(self) -> None:
        param = _param("search_metrics_awstats", "date")

        assert "2024-01-01" in _refused(param, {"min": "2020-01-01"})


class TestADatasetAndAStep:
    @pytest.mark.parametrize("raw", ["123", 123])
    def test_a_dataset_id_reads(self, raw: JsonValue) -> None:
        assert WDKDatasetParam(name="ds").read_stated(raw) == InputDatasetValue(
            dataset_id="123"
        )

    @pytest.mark.parametrize("raw", ["abc", "0", 0, -4, True])
    def test_a_dataset_id_is_a_positive_integer(self, raw: JsonValue) -> None:
        assert "ds takes" in _refused(WDKDatasetParam(name="ds"), raw)

    @pytest.mark.parametrize("raw", ["", "12"])
    def test_a_step_id_reads(self, raw: str) -> None:
        assert WDKAnswerParam(name="step").read_stated(raw) == InputStepValue(
            step_id=raw
        )

    @pytest.mark.parametrize("raw", ["abc", 12, True])
    def test_a_step_id_is_an_integer_string(self, raw: JsonValue) -> None:
        assert "step takes" in _refused(WDKAnswerParam(name="step"), raw)


class TestANumberStringWithALength:
    _PARAM = WDKStringParam(name="s", is_number=True, length=3)

    def test_a_short_number_reads(self) -> None:
        assert _wire(self._PARAM, 5.0) == "5"

    def test_a_number_longer_than_the_length_names_it(self) -> None:
        assert "at most 3 characters" in _refused(self._PARAM, 1e-8)


class TestDecimalText:
    @pytest.mark.parametrize(
        ("number", "text"),
        [
            (5.0, "5"),
            (1e-8, "0.00000001"),
            (1e22, "10000000000000000000000"),
            (-2.5, "-2.5"),
        ],
    )
    def test_the_shortest_decimal_without_an_exponent(
        self, number: float, text: str
    ) -> None:
        assert decimal_text(number) == text

    @pytest.mark.parametrize("number", [float("nan"), float("inf")])
    def test_a_value_with_no_decimal_is_refused(self, number: float) -> None:
        with pytest.raises(ValueError, match="decimal"):
            decimal_text(number)


def test_a_wire_default_fills_a_hidden_multi_pick() -> None:
    spec = ParamSpecNormalized(
        name="h",
        param_type="multi-pick-vocabulary",
        is_visible=False,
        initial_display_value='["a"]',
    )

    assert fill_site_set_defaults({"h": spec}, {}) == {
        "h": MultiPickValue(values=["a"])
    }


class TestTheCanonicalizer:
    def test_an_open_range_closes_to_the_declared_maximum(self) -> None:
        spec = ParamSpecNormalized(name="r", param_type="number-range", max=10)

        assert ParameterCanonicalizer({"r": spec}).canonicalize(
            {"r": NumberRangeValue(min=2)}
        ) == {"r": NumberRangeValue(min=2, max=10)}

    def test_a_single_pick_matches_its_term(self) -> None:
        spec = ParamSpecNormalized(
            name="s",
            param_type="single-pick-vocabulary",
            vocabulary=[WDKVocabTerm(("t1", "Term one", None))],
        )

        assert ParameterCanonicalizer({"s": spec}).canonicalize(
            {"s": SinglePickValue(value="Term one")}
        ) == {"s": SinglePickValue(value="t1")}

    def test_a_list_is_never_read_as_a_range(self) -> None:
        spec = ParamSpecNormalized(name="r", param_type="number-range", min=0, max=10)

        with pytest.raises(ValidationError):
            ParameterCanonicalizer({"r": spec}).canonicalize(
                {"r": MultiPickValue(values=["2", "8"])}
            )

    def test_the_range_wire_is_both_ends(self) -> None:
        spec = ParamSpecNormalized(name="r", param_type="number-range", min=0)

        closed = ParameterCanonicalizer({"r": spec}).canonicalize(
            {"r": NumberRangeValue(max=4)}
        )

        assert json.loads(closed["r"].to_wire()) == {"min": 0, "max": 4}


def test_a_dataset_schema_takes_a_positive_integer_id() -> None:
    assert WDKDatasetParam(name="ds").stated_schema() == {
        "anyOf": [
            {"type": "integer"},
            {"pattern": "^[1-9][0-9]*$", "type": "string"},
        ]
    }


@pytest.mark.skipif(needs_qa_recording(_ORTHOLOGS), reason=NEEDS_QA_RECORDING)
def test_a_recorded_step_schema_takes_an_id_or_the_empty_value() -> None:
    param = _param("search_genes_by_orthologs", "gene_result")

    assert param.stated_schema() == {
        "anyOf": [
            {"pattern": "^[0-9]+$", "type": "string"},
            {"const": "", "type": "string"},
        ]
    }


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS), reason=NEEDS_QA_RECORDING)
class TestAnEmptyValueIsReadAsItsDeclarationAllows:
    def test_a_number_string_that_allows_it_reads_the_empty_value(self) -> None:
        param = _param("search_genes_by_ngs_snps", "occurrences_upper")

        assert param.read_stated("") == StringValue(value="")

    def test_its_schema_offers_the_empty_value(self) -> None:
        param = _param("search_genes_by_ngs_snps", "occurrences_upper")
        schema: dict[str, Any] = param.stated_schema()

        assert {"const": "", "type": "string"} in schema["anyOf"]

    def test_its_refusal_names_the_empty_value(self) -> None:
        param = _param("search_genes_by_ngs_snps", "occurrences_upper")

        assert 'or "" to leave it empty' in _refused(param, "x")

    def test_a_number_string_that_does_not_allow_it_refuses_it(self) -> None:
        param = _param("search_genes_by_ngs_snps", "occurrences_lower")

        assert "occurrences_lower takes a value, not the empty value ''" in (
            _refused(param, "")
        )

    def test_a_multi_pick_that_does_not_allow_it_refuses_no_terms(self) -> None:
        param = _param("search_genes_by_ngs_snps", "organismSinglePick")

        assert "organismSinglePick takes" in _refused(param, [])


_VARIANTS = "wdk/search_genes_by_variant_characteristics.json"
_LOCATION = "wdk/search_genes_by_location.json"


def _each_kind() -> list[WDKParameter]:
    """One declaration of every kind that refuses an empty value."""
    return [
        _param("search_genes_by_ngs_snps", "occurrences_lower"),
        WDKNumberParam(name="n", min=0, max=10),
        WDKNumberRangeParam(name="nr", min=0, max=10),
        WDKDateParam(name="d"),
        _param("search_metrics_awstats", "date"),
        WDKTimestampParam(name="t"),
        _param("search_genes_by_ngs_snps", "ReadFrequencyPercent"),
        _param("search_genes_by_ngs_snps", "organismSinglePick"),
        _param("search_genes_by_ngs_snps", "variation_sample_meta"),
        WDKDatasetParam(name="ds"),
    ]


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS), reason=NEEDS_QA_RECORDING)
@pytest.mark.skipif(needs_qa_recording(_AWSTATS), reason=NEEDS_QA_RECORDING)
class TestAnEmptyValueOnEachKind:
    def test_every_kind_is_covered(self) -> None:
        assert {p.type for p in _each_kind()} == set(get_args(ParamKind)) - {
            "input-step"
        }

    @pytest.mark.parametrize("index", range(10))
    def test_a_declaration_that_does_not_allow_it_refuses_it(self, index: int) -> None:
        param = _each_kind()[index]

        assert not param.allow_empty_value
        assert f"{param.name} takes" in _refused(param, "")

    @pytest.mark.parametrize("index", range(10))
    def test_the_same_declaration_allowing_it_reads_its_empty_value(
        self, index: int
    ) -> None:
        param = _each_kind()[index].model_copy(update={"allow_empty_value": True})

        assert param.read_stated("") == empty_value(param.type)

    @pytest.mark.parametrize(
        ("kind", "wire"),
        [
            ("string", ""),
            ("number", ""),
            ("number-range", ""),
            ("date", ""),
            ("date-range", ""),
            ("timestamp", ""),
            ("single-pick-vocabulary", ""),
            ("multi-pick-vocabulary", "[]"),
            ("filter", ""),
            ("input-dataset", ""),
            ("input-step", ""),
        ],
    )
    def test_an_empty_value_goes_out_as_the_empty_wire_value(
        self, kind: ParamKind, wire: str
    ) -> None:
        assert empty_value(kind).to_wire() == wire

    @pytest.mark.parametrize("kind", get_args(ParamKind))
    def test_the_empty_wire_value_reads_back_as_the_empty_value(
        self, kind: ParamKind
    ) -> None:
        assert from_wire(kind, empty_value(kind).to_wire()) == empty_value(kind)


@pytest.mark.skipif(needs_qa_recording(_VARIANTS), reason=NEEDS_QA_RECORDING)
@pytest.mark.parametrize("raw", ["", []])
def test_a_recorded_multi_pick_that_allows_it_reads_no_terms(raw: JsonValue) -> None:
    param = _param("search_genes_by_variant_characteristics", "organism_select_none")

    assert param.allow_empty_value
    assert _wire(param, raw) == "[]"


@pytest.mark.skipif(needs_qa_recording(_LOCATION), reason=NEEDS_QA_RECORDING)
class TestTheSelectedCount:
    def test_two_terms_past_the_maximum_of_one_are_refused(self) -> None:
        param = _param("search_genes_by_location", "organismSinglePick")
        terms: list[JsonValue] = [o.value for o in flatten_vocab(param.vocabulary)[:2]]

        refusal = _refused(param, terms)

        assert "organismSinglePick takes a list of terms from" in refusal
        assert "(exactly 1)" in refusal

    def test_one_term_reads(self) -> None:
        param = _param("search_genes_by_location", "organismSinglePick")

        assert param.read_stated(["Plasmodium falciparum 3D7"]) == MultiPickValue(
            values=["Plasmodium falciparum 3D7"]
        )

    def test_the_schema_states_both_counts(self) -> None:
        param = _param("search_genes_by_location", "organismSinglePick")
        schema: dict[str, Any] = param.stated_schema()

        assert (schema["minItems"], schema["maxItems"]) == (1, 1)


class TestAnEmptyFilterIsNotAFilterWithNoClauses:
    def test_the_two_are_distinct_values(self) -> None:
        assert empty_value("filter") != FilterValue()

    def test_no_clauses_goes_out_as_an_empty_clause_list(self) -> None:
        assert FilterValue().to_wire() == '{"filters":[]}'

    def test_each_wire_reads_back_as_its_own_value(self) -> None:
        assert from_wire("filter", "") == empty_value("filter")
        assert from_wire("filter", '{"filters": []}') == FilterValue()

    def test_an_empty_value_holds_no_clause(self) -> None:
        with pytest.raises(PydanticValidationError):
            FilterValue.model_validate(
                {
                    "empty": True,
                    "filters": [
                        {
                            "field": "sex",
                            "type": "string",
                            "isRange": False,
                            "includeUnknown": False,
                            "value": ["female"],
                        }
                    ],
                }
            )


def _spec(param: WDKParameter) -> ParamSpecNormalized:
    return ParamSpecNormalized(
        name=param.name,
        param_type=param.type,
        allow_empty_value=param.allow_empty_value,
        min_selected_count=param.min_selected_count,
        max_selected_count=param.max_selected_count,
        vocabulary=param.vocabulary,
        is_number=param.is_number,
        min=param.min,
        max=param.max,
        min_date=param.min_date,
        max_date=param.max_date,
        max_length=param.length or None,
        display_type=param.display_type,
    )


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS), reason=NEEDS_QA_RECORDING)
@pytest.mark.skipif(needs_qa_recording(_AWSTATS), reason=NEEDS_QA_RECORDING)
class TestTheCanonicalizerRefusesAnEmptyValueItsParameterRefuses:
    @pytest.mark.parametrize("index", range(10))
    def test_with_the_readers_words(self, index: int) -> None:
        param = _each_kind()[index]
        empty = empty_value(param.type)

        with pytest.raises(StatedValuesError) as canonical:
            ParameterCanonicalizer({param.name: _spec(param)}).canonicalize(
                {param.name: empty}
            )

        assert str(canonical.value) == _refused(param, empty.to_decoded())

    @pytest.mark.parametrize("index", range(10))
    def test_and_keeps_it_where_its_parameter_allows_it(self, index: int) -> None:
        param = _each_kind()[index].model_copy(update={"allow_empty_value": True})
        empty = empty_value(param.type)

        assert ParameterCanonicalizer({param.name: _spec(param)}).canonicalize(
            {param.name: empty}
        ) == {param.name: empty}


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS), reason=NEEDS_QA_RECORDING)
@pytest.mark.skipif(needs_qa_recording(_AWSTATS), reason=NEEDS_QA_RECORDING)
class TestAHeldValueIsReadAsWdkHoldsIt:
    def test_a_recorded_empty_number_string_reads_its_empty_value(self) -> None:
        param = _param("search_genes_by_ngs_snps", "occurrences_lower")

        held = ParameterCanonicalizer({param.name: _spec(param)}).held({param.name: ""})

        assert held == {param.name: StringValue(value="")}

    @pytest.mark.parametrize("index", range(10))
    def test_every_kind_reads_its_empty_wire_form(self, index: int) -> None:
        param = _each_kind()[index]
        empty = empty_value(param.type)

        held = ParameterCanonicalizer({param.name: _spec(param)}).held(
            {param.name: empty.to_wire()}
        )

        assert held == {param.name: empty}

    def test_a_wire_form_no_kind_reads_is_kept_as_wdk_holds_it(self) -> None:
        param = WDKNumberParam(name="n", min=0, max=10)

        held = ParameterCanonicalizer({"n": _spec(param)}).held({"n": "abc"})

        assert held == {"n": HeldValue(wire="abc")}

    def test_a_term_the_vocabulary_lost_is_kept_as_decoded(self) -> None:
        param = _param("search_genes_by_ngs_snps", "ReadFrequencyPercent")

        held = ParameterCanonicalizer({param.name: _spec(param)}).held(
            {param.name: "10%"}
        )

        assert held == {param.name: SinglePickValue(value="10%")}


def test_one_text_refuses_an_empty_value_on_both_paths() -> None:
    param = WDKNumberParam(name="n", min=0, max=10)

    with pytest.raises(StatedValuesError) as canonical:
        ParameterCanonicalizer({"n": _spec(param)}).canonicalize(
            {"n": empty_value("number")}
        )

    assert str(canonical.value) == _refused(param, "")
    assert "n takes a value, not the empty value ''" in str(canonical.value)
