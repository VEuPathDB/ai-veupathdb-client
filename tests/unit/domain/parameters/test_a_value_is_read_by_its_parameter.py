from __future__ import annotations

import json

import pytest
from pydantic import JsonValue

from veupathdb.domain.parameters import (
    ParameterCanonicalizer,
    StatedValuesError,
    decimal_text,
    fill_site_set_defaults,
    read_stated_values,
)
from veupathdb.domain.parameters.specs import ParamSpecNormalized
from veupathdb.domain.parameters.values import (
    DateRangeValue,
    DateValue,
    InputDatasetValue,
    InputStepValue,
    MultiPickValue,
    NumberRangeValue,
    SinglePickValue,
)
from veupathdb.domain.parameters.wdk_vocab import WDKVocabTerm
from veupathdb.errors import ValidationError
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse
from veupathdb.wdk.wdk_parameters import (
    WDKAnswerParam,
    WDKDatasetParam,
    WDKDateParam,
    WDKNumberParam,
    WDKNumberRangeParam,
    WDKParameter,
    WDKStringParam,
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
        [(5.0, "5"), (1e-8, "0.00000001"), ("5.0", "5"), (0.25, "0.25")],
    )
    def test_a_number_goes_out_as_its_shortest_decimal(
        self, raw: JsonValue, wire: str
    ) -> None:
        param = _param("search_genes_by_ngs_snps", "MinPercentMinorAlleles")

        assert param.read_stated(raw).to_wire() == wire

    @pytest.mark.parametrize("raw", [float("nan"), float("inf"), True, "5,000"])
    def test_a_value_that_is_not_a_number_is_refused(self, raw: JsonValue) -> None:
        param = _param("search_genes_by_ngs_snps", "MinPercentMinorAlleles")

        assert "MinPercentMinorAlleles takes" in _refused(param, raw)


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS), reason=NEEDS_QA_RECORDING)
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
            "ReadFrequencyPercent": "10%",
        }

        with pytest.raises(StatedValuesError) as refusal:
            read_stated_values(_params("search_genes_by_ngs_snps"), stated)

        assert len(refusal.value.faults) == 2

    def test_every_name_the_declaration_holds_is_read(self) -> None:
        read = read_stated_values(
            _params("search_genes_by_ngs_snps"),
            {"MinPercentMinorAlleles": 5.0, "ReadFrequencyPercent": "80%"},
        )

        assert {name: value.to_wire() for name, value in read.items()} == {
            "MinPercentMinorAlleles": "5",
            "ReadFrequencyPercent": "80%",
        }


class TestANumber:
    _PARAM = WDKNumberParam(name="n", min=0, max=100)

    def test_a_float_goes_out_without_a_point(self) -> None:
        assert self._PARAM.read_stated(5.0).to_wire() == "5"

    def test_a_value_above_the_maximum_names_it(self) -> None:
        assert "100" in _refused(self._PARAM, 101)

    def test_a_boolean_is_refused(self) -> None:
        assert "n takes" in _refused(self._PARAM, True)


class TestANumberRange:
    def test_an_open_end_closes_from_the_declared_limit(self) -> None:
        param = WDKNumberRangeParam(name="r", min=0, max=10)

        assert param.read_stated({"min": 2}).to_wire() == '{"min": 2.0, "max": 10.0}'

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
        assert self._PARAM.read_stated(5.0).to_wire() == "5"

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


def _id_pattern(model: type[InputDatasetValue | InputStepValue], key: str) -> JsonValue:
    properties: dict[str, dict[str, JsonValue]] = model.model_json_schema()[
        "properties"
    ]
    return properties[key]["pattern"]


def test_a_dataset_schema_carries_the_value_model_pattern() -> None:
    assert WDKDatasetParam(name="ds").stated_schema() == {
        "anyOf": [
            {"type": "integer"},
            {"pattern": _id_pattern(InputDatasetValue, "datasetId"), "type": "string"},
        ]
    }


@pytest.mark.skipif(needs_qa_recording(_ORTHOLOGS), reason=NEEDS_QA_RECORDING)
def test_a_recorded_step_schema_carries_the_value_model_pattern() -> None:
    param = _param("search_genes_by_orthologs", "gene_result")

    assert param.stated_schema() == {
        "pattern": _id_pattern(InputStepValue, "stepId"),
        "type": "string",
    }
