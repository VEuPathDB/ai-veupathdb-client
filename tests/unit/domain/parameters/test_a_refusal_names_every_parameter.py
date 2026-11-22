from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from veupathdb.domain.parameters import (
    MultiPickValue,
    ParameterCanonicalizer,
    SinglePickValue,
    StatedValuesError,
    VocabularyEntryError,
    read_stated_values,
)
from veupathdb.domain.parameters.specs import ParamSpecNormalized
from veupathdb.errors import ValidationError, joined_refusal
from veupathdb.json_types import JSONArray
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse
from veupathdb.wdk.wdk_parameters import WDKParameter

_SNPS = "search_genes_by_ngs_snps"


def _sheet() -> list[WDKParameter]:
    search = WDKSearchResponse.model_validate(load_recorded(_SNPS).json_body())
    return list(search.search_data.parameters or [])


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


class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore")

    param: str
    detail: str


_ROWS = TypeAdapter(list[_Row])


def _params(errors: JSONArray | None) -> list[str]:
    return [row.param for row in _ROWS.validate_python(errors)]


def _assert_one_sentence_per_row(refusal: ValidationError) -> None:
    rows = _ROWS.validate_python(refusal.errors)
    assert rows
    assert all(row.detail and "\n" not in row.detail for row in rows)


_TWO_ENTRIES: dict[str, JsonValue] = {
    "snp_class": "non-synonymous",
    "ReadFrequencyPercent": "95 percent",
}


@pytest.mark.skipif(needs_qa_recording(f"wdk/{_SNPS}.json"), reason=NEEDS_QA_RECORDING)
class TestAStatedCallNamesEveryParameter:
    def test_every_entry_fault_is_one_refusal_in_declaration_order(self) -> None:
        with pytest.raises(VocabularyEntryError) as refused:
            read_stated_values(_sheet(), _TWO_ENTRIES)

        assert [p for p, _ in refused.value.faults] == [
            "ReadFrequencyPercent",
            "snp_class",
        ]
        assert _params(refused.value.errors) == ["ReadFrequencyPercent", "snp_class"]
        _assert_one_sentence_per_row(refused.value)

    def test_a_shape_fault_comes_first_and_every_entry_fault_follows(self) -> None:
        stated: dict[str, JsonValue] = {
            **_TWO_ENTRIES,
            "MinPercentMinorAlleles": {"x": 1},
        }

        with pytest.raises(StatedValuesError) as refused:
            read_stated_values(_sheet(), stated)

        faults = refused.value.faults
        assert [f.name for f in faults] == [
            "MinPercentMinorAlleles",
            "ReadFrequencyPercent",
            "snp_class",
        ]
        assert all(f.name in f.text for f in faults)
        assert [f.read for f in faults[1:]] == ["95 percent", "non-synonymous"]
        _assert_one_sentence_per_row(refused.value)


@pytest.mark.skipif(needs_qa_recording(f"wdk/{_SNPS}.json"), reason=NEEDS_QA_RECORDING)
class TestACanonicalizedCallNamesEveryParameter:
    def test_an_unknown_name_and_a_wrong_kind_are_one_refusal(self) -> None:
        specs = {param.name: _spec(param) for param in _sheet()}

        with pytest.raises(ValidationError) as refused:
            ParameterCanonicalizer(specs).canonicalize(
                {
                    "snp_klass": SinglePickValue(value="Missense"),
                    "snp_class": MultiPickValue(values=["Missense"]),
                }
            )

        assert _params(refused.value.errors) == ["snp_klass", "snp_class"]
        _assert_one_sentence_per_row(refused.value)

    def test_an_unnamed_entry_row_carries_its_sentence(self) -> None:
        specs = {param.name: _spec(param) for param in _sheet()}

        with pytest.raises(VocabularyEntryError) as refused:
            ParameterCanonicalizer(specs).canonicalize(
                {"snp_class": SinglePickValue(value="non-synonymous")}
            )

        _assert_one_sentence_per_row(refused.value)


class TestJoinedRefusal:
    def test_one_refusal_is_returned_as_it_is(self) -> None:
        refusal = ValidationError(detail="a", errors=[{"param": "a", "detail": "a"}])

        assert joined_refusal([refusal]) is refusal

    def test_several_refusals_are_one_with_every_row(self) -> None:
        first = ValidationError(detail="a.", errors=[{"param": "a", "detail": "a."}])
        second = ValidationError(detail="b.", errors=[{"param": "b", "detail": "b."}])

        joined = joined_refusal([first, second])

        assert joined.title == "Invalid parameter values"
        assert joined.detail == "a.\nb."
        assert joined.errors == [
            {"param": "a", "detail": "a."},
            {"param": "b", "detail": "b."},
        ]
