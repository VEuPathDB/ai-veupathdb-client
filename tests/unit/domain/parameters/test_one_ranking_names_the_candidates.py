from __future__ import annotations

import pytest
from pydantic import ValidationError

from veupathdb.domain.parameters import (
    DECIDED_CANDIDATES,
    SHOWN_CANDIDATES,
    Resolution,
    VocabOption,
    exact_or_candidates,
    flatten_vocab,
    rank_entries,
    read_options,
)
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse

pytestmark = pytest.mark.skipif(
    needs_qa_recording(
        "wdk/search_genes_by_taxon.json",
        "wdk/search_genes_by_gene_type.json",
        "wdk/search_genes_by_metabolic_pathway_hagai.json",
        "wdk/search_genes_by_ngs_snps.json",
    ),
    reason=NEEDS_QA_RECORDING,
)

_3D7 = "Plasmodium falciparum 3D7"


def _options(fixture: str, name: str) -> list[VocabOption]:
    search = WDKSearchResponse.model_validate(
        load_recorded(fixture).json_body()
    ).search_data
    [param] = [p for p in search.parameters or [] if p.name == name]
    return flatten_vocab(param.vocabulary)


def _taxon() -> list[VocabOption]:
    return _options("search_genes_by_taxon", "organism")


def _gene_type() -> list[VocabOption]:
    return _options("search_genes_by_gene_type", "geneType")


def _hagai() -> list[VocabOption]:
    return _options("search_genes_by_metabolic_pathway_hagai", "metabolic_pathway")


def _snp_class() -> list[VocabOption]:
    return _options("search_genes_by_ngs_snps", "snp_class")


def test_the_limits_hold_one_card_and_one_decisions_choice() -> None:
    assert (SHOWN_CANDIDATES, DECIDED_CANDIDATES) == (5, 254)


@pytest.mark.parametrize(
    "phrase", ["Plasmodium  falciparum 3D7", "plasmodium falciparum 3D7"]
)
def test_case_and_spacing_name_the_entry_exactly(phrase: str) -> None:
    resolution = exact_or_candidates(_taxon(), phrase, SHOWN_CANDIDATES)

    assert resolution.how == "exact"
    assert resolution.value == _3D7
    assert resolution.candidates == []
    assert resolution.settled


@pytest.mark.parametrize(
    ("phrase", "first"),
    [("Pf3D7", _3D7), ("PbANKA", "Plasmodium berghei ANKA")],
)
def test_an_abbreviation_ranks_its_entry_first_and_settles_nothing(
    phrase: str, first: str
) -> None:
    resolution = exact_or_candidates(_taxon(), phrase, SHOWN_CANDIDATES)

    assert resolution.how == "unsettled"
    assert resolution.value is None
    assert not resolution.settled
    assert resolution.candidates[0].value == first


def test_a_species_initial_ranks_the_reference_strain() -> None:
    ranked = rank_entries(_taxon(), "P. falciparum", SHOWN_CANDIDATES)

    assert _3D7 in [option.value for option in ranked]


def test_a_word_inside_another_is_a_candidate_and_never_a_value() -> None:
    options = _snp_class()

    resolution = exact_or_candidates(options, "non-synonymous", DECIDED_CANDIDATES)

    assert resolution.value is None
    assert resolution.candidates[0].value == "Synonymous"
    assert {o.value for o in resolution.candidates} == {o.value for o in options}
    assert len(options) == 6


def test_the_spelling_neighbours_follow_the_lexical_entries() -> None:
    options = _hagai()
    phrase = "citric acid cycle"

    ranked = rank_entries(options, phrase, DECIDED_CANDIDATES)

    lexical = read_options(options, [phrase], request_terms=[phrase]).options
    assert len(lexical) == 15
    assert ranked[:15] == lexical
    assert [o.value for o in ranked].index("Mitochondrial TCA cycle") == 8
    assert ranked[15].value == "Actin and filaments"


def test_a_plural_ranks_its_singular_entry_first() -> None:
    ranked = rank_entries(_gene_type(), "pseudogenes", SHOWN_CANDIDATES)

    assert ranked[0].display == "pseudogene"


def test_a_label_in_other_case_is_exact() -> None:
    resolution = exact_or_candidates(_gene_type(), "Protein Coding", SHOWN_CANDIDATES)

    assert (resolution.how, resolution.value) == ("exact", "protein coding")


def test_a_number_in_another_spelling_is_exact() -> None:
    options = [VocabOption(value="0.5", display="0.5")]

    resolution = exact_or_candidates(options, "0.50", SHOWN_CANDIDATES)

    assert (resolution.how, resolution.value) == ("exact", "0.5")
    assert resolution.candidates == []


@pytest.mark.parametrize("phrase", ["Pf3D7", "P. falciparum", "malaria", "x"])
@pytest.mark.parametrize("limit", [1, 3, SHOWN_CANDIDATES])
def test_a_ranking_holds_each_value_once_within_its_limit(
    phrase: str, limit: int
) -> None:
    ranked = rank_entries(_taxon(), phrase, limit)

    values = [option.value for option in ranked]
    assert len(values) == len(set(values))
    assert 0 < len(values) <= limit


def test_nothing_to_rank_is_how_none() -> None:
    resolution = exact_or_candidates([], "Pf3D7", SHOWN_CANDIDATES)

    assert (resolution.how, resolution.value, resolution.candidates) == (
        "none",
        None,
        [],
    )


def test_an_exact_resolution_needs_its_value() -> None:
    with pytest.raises(ValidationError):
        Resolution(phrase="x", how="exact", candidates=[])


def test_an_unsettled_resolution_holds_no_value() -> None:
    with pytest.raises(ValidationError):
        Resolution(
            phrase="x",
            how="unsettled",
            value="x",
            candidates=[VocabOption(value="x", display="x")],
        )


def test_an_unsettled_resolution_holds_candidates() -> None:
    with pytest.raises(ValidationError):
        Resolution(phrase="x", how="unsettled", candidates=[])


def test_none_holds_no_candidates() -> None:
    with pytest.raises(ValidationError):
        Resolution(
            phrase="x", how="none", candidates=[VocabOption(value="x", display="x")]
        )
