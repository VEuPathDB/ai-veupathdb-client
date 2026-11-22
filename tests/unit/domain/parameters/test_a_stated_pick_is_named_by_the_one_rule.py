"""A stated pick names a vocabulary entry by the one exact step, or is refused with candidates."""

from __future__ import annotations

import pytest
from pydantic import JsonValue

from veupathdb.domain.parameters import (
    MultiPickValue,
    SinglePickValue,
    StatedValuesError,
    VocabOption,
    VocabularyEntryError,
    entries_or_refusal,
    exact_entry,
    read_stated_values,
)
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse
from veupathdb.wdk.wdk_parameters import WDKParameter

_SNPS = "search_genes_by_ngs_snps"
_TAXON = "search_genes_by_taxon"


def _param(fixture: str, name: str) -> WDKParameter:
    search = WDKSearchResponse.model_validate(load_recorded(fixture).json_body())
    return next(p for p in search.search_data.parameters or [] if p.name == name)


def _refusal(param: WDKParameter, raw: JsonValue) -> VocabularyEntryError:
    with pytest.raises(VocabularyEntryError) as refused:
        read_stated_values([param], {param.name: raw})
    return refused.value


@pytest.mark.skipif(needs_qa_recording(f"wdk/{_SNPS}.json"), reason=NEEDS_QA_RECORDING)
class TestASmallFlatVocabulary:
    def test_a_term_in_another_case_names_its_entry(self) -> None:
        param = _param(_SNPS, "snp_class")

        assert param.read_stated("missense") == SinglePickValue(value="Missense")
        assert read_stated_values([param], {"snp_class": "missense"}) == {
            "snp_class": SinglePickValue(value="Missense")
        }

    def test_a_term_no_entry_spells_is_refused_with_ranked_candidates(self) -> None:
        refused = _refusal(_param(_SNPS, "snp_class"), "non-synonymous")

        [(name, resolution)] = refused.faults
        assert name == "snp_class"
        assert resolution.value is None
        assert "Synonymous" in [c.value for c in resolution.candidates]
        assert len(resolution.candidates) <= 5

    def test_the_schema_still_lists_the_entries(self) -> None:
        param = _param(_SNPS, "snp_class")

        assert param.stated_schema()["enum"] == [
            "All SNVs",
            "Coding",
            "Unclassified",
            "Missense",
            "Stop-gained",
            "Synonymous",
        ]

    def test_a_value_of_another_shape_is_still_refused_by_its_shape(self) -> None:
        with pytest.raises(StatedValuesError, match="snp_class takes one of"):
            read_stated_values([_param(_SNPS, "snp_class")], {"snp_class": 5})


@pytest.mark.skipif(needs_qa_recording(f"wdk/{_TAXON}.json"), reason=NEEDS_QA_RECORDING)
class TestALongVocabulary:
    def test_two_unnamed_terms_are_one_refusal_with_two_faults(self) -> None:
        refused = _refusal(_param(_TAXON, "organism"), ["Pf3D7", "PbANKA"])

        assert [(n, r.phrase) for n, r in refused.faults] == [
            ("organism", "Pf3D7"),
            ("organism", "PbANKA"),
        ]
        assert refused.faults[0][1].candidates[0].value == "Plasmodium falciparum 3D7"

    def test_a_named_term_reads_as_its_entry(self) -> None:
        param = _param(_TAXON, "organism")

        assert param.read_stated(["plasmodium  falciparum 3d7"]) == MultiPickValue(
            values=["Plasmodium falciparum 3D7"]
        )

    def test_a_shape_fault_is_raised_before_any_entry_is_read(self) -> None:
        taxon = _param(_TAXON, "organism")
        with pytest.raises(StatedValuesError):
            read_stated_values([taxon], {"organism": 7})


class TestTheExactStep:
    _OPTIONS = (
        VocabOption(value="Missense", display="Missense"),
        VocabOption(value="7", display="seven"),
    )

    @pytest.mark.parametrize(
        ("phrase", "value"),
        [
            ("missense", "Missense"),
            (" MISSENSE ", "Missense"),
            ("7.0", "7"),
            ("non-synonymous", None),
        ],
    )
    def test_the_exact_step_names_an_entry_or_none(
        self, phrase: str, value: str | None
    ) -> None:
        found = exact_entry(self._OPTIONS, phrase)

        assert (None if found is None else found.value) == value


class TestTheBindOrRefuseStep:
    _OPTIONS = (VocabOption(value="Missense", display="Missense"),)

    def test_every_term_names_its_entry(self) -> None:
        assert entries_or_refusal("snp_class", self._OPTIONS, ["missense"]) == [
            "Missense"
        ]

    def test_no_vocabulary_keeps_the_terms(self) -> None:
        assert entries_or_refusal("organism", (), ["Pf3D7"]) == ["Pf3D7"]

    def test_every_unnamed_term_is_one_fault_of_one_refusal(self) -> None:
        with pytest.raises(VocabularyEntryError) as refused:
            entries_or_refusal("snp_class", self._OPTIONS, ["x", "missense", "y"])

        assert [r.phrase for _, r in refused.value.faults] == ["x", "y"]
