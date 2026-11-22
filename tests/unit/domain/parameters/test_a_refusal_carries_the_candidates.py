from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, TypeAdapter

from veupathdb.domain.parameters import (
    SHOWN_CANDIDATES,
    MultiPickValue,
    ParameterCanonicalizer,
    ParamSpecNormalized,
    PhyleticTree,
    Resolution,
    SinglePickValue,
    VocabOption,
    VocabularyEntryError,
    entry_name,
)
from veupathdb.errors import ValidationError
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKParameter, phyletic_tree_of
from veupathdb.wdk.wdk_models import WDKSearchResponse


class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore")

    param: str
    value: str


def _parameter(fixture: str, name: str) -> WDKParameter:
    search = WDKSearchResponse.model_validate(load_recorded(fixture).json_body())
    return next(p for p in search.search_data.parameters or [] if p.name == name)


def _canonicalizer(fixture: str, name: str) -> ParameterCanonicalizer:
    param = _parameter(fixture, name)
    spec = ParamSpecNormalized(
        name=param.name, param_type=param.type, vocabulary=param.vocabulary
    )
    return ParameterCanonicalizer({name: spec})


def _phyletic_tree() -> PhyleticTree:
    search = WDKSearchResponse.model_validate(
        load_recorded("search_genes_by_ortholog_pattern").json_body()
    )
    tree = phyletic_tree_of(search.search_data.parameters or [])
    assert tree is not None
    return tree


needs_gene_type = pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_gene_type.json"),
    reason=NEEDS_QA_RECORDING,
)
needs_snps = pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_ngs_snps.json"),
    reason=NEEDS_QA_RECORDING,
)
needs_taxon = pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_taxon.json"),
    reason=NEEDS_QA_RECORDING,
)
needs_ortholog_pattern = pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_ortholog_pattern.json"),
    reason=NEEDS_QA_RECORDING,
)


@needs_gene_type
def test_a_term_in_another_case_is_the_term() -> None:
    canonical = _canonicalizer("search_genes_by_gene_type", "geneType").canonicalize(
        {"geneType": MultiPickValue(values=["Protein Coding"])}
    )

    assert canonical == {"geneType": MultiPickValue(values=["protein coding"])}


@needs_snps
def test_a_single_pick_in_lower_case_is_the_term() -> None:
    canonical = _canonicalizer("search_genes_by_ngs_snps", "snp_class").canonicalize(
        {"snp_class": SinglePickValue(value="missense")}
    )

    assert canonical == {"snp_class": SinglePickValue(value="Missense")}


@needs_taxon
def test_a_doubled_space_is_the_term() -> None:
    canonical = _canonicalizer("search_genes_by_taxon", "organism").canonicalize(
        {"organism": MultiPickValue(values=["Plasmodium  falciparum 3D7"])}
    )

    assert canonical == {
        "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])
    }


@needs_taxon
def test_a_text_no_entry_spells_is_refused_with_the_ranked_candidates() -> None:
    with pytest.raises(VocabularyEntryError) as refused:
        _canonicalizer("search_genes_by_taxon", "organism").canonicalize(
            {"organism": MultiPickValue(values=["Pf3D7"])}
        )

    name, resolution = refused.value.faults[0]
    detail = refused.value.detail or ""
    assert name == "organism"
    assert resolution.candidates[0].value == "Plasmodium falciparum 3D7"
    assert len(resolution.candidates) == SHOWN_CANDIDATES
    assert "get_parameter_options" not in detail
    assert "Trypanosoma" not in detail
    assert detail.startswith("organism has no entry 'Pf3D7'. Candidates: ")


@needs_taxon
def test_the_refusal_states_each_candidate_on_the_wire() -> None:
    with pytest.raises(VocabularyEntryError) as refused:
        _canonicalizer("search_genes_by_taxon", "organism").canonicalize(
            {"organism": MultiPickValue(values=["Pf3D7"])}
        )

    resolution = refused.value.faults[0][1]
    assert refused.value.errors == [
        {
            "param": "organism",
            "detail": refused.value.detail,
            "value": "Pf3D7",
            "candidates": [
                {"value": c.value, "display": c.display} for c in resolution.candidates
            ],
        }
    ]


@needs_taxon
def test_every_unnamed_pick_is_one_fault() -> None:
    with pytest.raises(VocabularyEntryError) as refused:
        _canonicalizer("search_genes_by_taxon", "organism").canonicalize(
            {
                "organism": MultiPickValue(
                    values=["Pf3D7", "Plasmodium falciparum 3D7", "PvP01"]
                )
            }
        )

    assert [(n, r.phrase) for n, r in refused.value.faults] == [
        ("organism", "Pf3D7"),
        ("organism", "PvP01"),
    ]
    assert len((refused.value.detail or "").splitlines()) == 2


def test_a_refusal_with_no_candidate_says_none_is_near() -> None:
    refusal = VocabularyEntryError(
        [("snp_class", Resolution(phrase="nonsense", how="none", candidates=[]))]
    )

    assert (
        refusal.detail == "snp_class has no entry 'nonsense', and no entry is near it."
    )
    assert isinstance(refusal, ValidationError)


def test_the_detail_shows_only_the_first_candidates() -> None:
    candidates = [VocabOption(value=f"v{i}", display=f"d{i}") for i in range(7)]
    refusal = VocabularyEntryError(
        [("p", Resolution(phrase="x", how="unsettled", candidates=candidates))]
    )

    assert refusal.detail == (
        "p has no entry 'x'. Candidates: d0 (v0), d1 (v1), d2 (v2), d3 (v3), d4 (v4)."
    )


@needs_ortholog_pattern
class TestThePhyleticReaderReadsTheOneRule:
    def test_a_doubled_space_names_the_genome(self) -> None:
        assert _phyletic_tree().resolve_terms("Plasmodium  falciparum 3D7").codes == [
            "pfal"
        ]

    def test_a_code_in_another_case_names_it(self) -> None:
        assert _phyletic_tree().resolve_terms("PFAL").codes == ["pfal"]

    def test_a_clade_code_names_itself(self) -> None:
        assert _phyletic_tree().resolve_terms("APIC").codes == ["APIC"]

    def test_a_genus_names_no_node(self) -> None:
        resolved = _phyletic_tree().resolve_terms("Plasmodium")

        assert resolved.codes == []
        assert resolved.unknown == ["Plasmodium"]


@needs_taxon
@needs_gene_type
def test_every_parameter_with_an_unnamed_pick_is_refused_at_once() -> None:
    organism = _parameter("search_genes_by_taxon", "organism")
    gene_type = _parameter("search_genes_by_gene_type", "geneType")
    canonicalizer = ParameterCanonicalizer(
        {
            p.name: ParamSpecNormalized(
                name=p.name, param_type=p.type, vocabulary=p.vocabulary
            )
            for p in (organism, gene_type)
        }
    )

    with pytest.raises(VocabularyEntryError) as refused:
        canonicalizer.canonicalize(
            {
                "organism": MultiPickValue(values=["Pf3D7"]),
                "geneType": MultiPickValue(values=["mRNA"]),
            }
        )

    rows = TypeAdapter(list[_Row]).validate_python(refused.value.errors)
    assert [(row.param, row.value) for row in rows] == [
        ("organism", "Pf3D7"),
        ("geneType", "mRNA"),
    ]
    assert len((refused.value.detail or "").splitlines()) == 2


@needs_snps
def test_a_candidate_whose_display_is_its_value_is_named_once() -> None:
    with pytest.raises(VocabularyEntryError) as refused:
        _canonicalizer("search_genes_by_ngs_snps", "snp_class").canonicalize(
            {"snp_class": SinglePickValue(value="nonsense")}
        )

    detail = refused.value.detail or ""
    named = detail.split("Candidates: ", 1)[1].rstrip(".").split(", ")
    assert len(named) == SHOWN_CANDIDATES
    assert all("(" not in entry for entry in named)
    assert "Missense" in named


@pytest.mark.parametrize(
    ("option", "name"),
    [
        (
            VocabOption(value="pfal", display="Plasmodium falciparum 3D7"),
            "Plasmodium falciparum 3D7 (pfal)",
        ),
        (VocabOption(value="Missense", display="Missense"), "Missense"),
    ],
)
def test_an_entry_is_named_by_its_display_and_its_value(
    option: VocabOption, name: str
) -> None:
    assert entry_name(option) == name
