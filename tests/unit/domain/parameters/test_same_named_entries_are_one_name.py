from __future__ import annotations

import json
from pathlib import Path

from veupathdb.domain.parameters import (
    VocabOption,
    WDKVocabulary,
    exact_or_candidates,
    flatten_vocab,
    match_exact_option,
    read_options,
    same_named_groups,
    vocab_paths,
)
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKSearchResponse

_E1 = json.loads(
    (Path(__file__).parent / "e1_serine_threonine_kinase_lookup.json").read_text()
)
_E1_PHRASE = _E1["vocabLookup"]["matches"][0]["values"]


def _e1_options() -> list[VocabOption]:
    return [VocabOption.model_validate(v) for v in _E1["allowedValues"]]


def _e1_phrase_entries() -> list[VocabOption]:
    return [o for o in _e1_options() if o.value in _E1_PHRASE]


def _mass_spec_assays() -> list[VocabOption]:
    body = load_recorded("search_genes_by_mass_spec").json_body()
    search = WDKSearchResponse.model_validate(body).search_data
    [assay] = [p for p in search.parameters or [] if p.name == "ms_assay"]
    return flatten_vocab(assay.vocabulary)


def test_two_entries_past_their_accessions_share_one_name() -> None:
    assert same_named_groups(_e1_phrase_entries()) == [["IPR050205", "IPR050236"]]


def test_the_shared_name_names_no_single_entry() -> None:
    assert match_exact_option(_e1_options(), "serine/threonine-protein kinase") is None


def test_an_accession_still_names_its_entry() -> None:
    assert match_exact_option(_e1_options(), "IPR050236") == "IPR050236"


def test_a_label_three_organisms_share_names_none_of_them() -> None:
    assays = _mass_spec_assays()

    assert match_exact_option(assays, "female gametocytes") is None
    assert exact_or_candidates(assays, "female gametocytes", 5).how == "unsettled"
    assert match_exact_option(
        assays, "female gametocytes_Plasmodium falciparum 3D7"
    ) == ("female gametocytes_Plasmodium falciparum 3D7")


def test_the_lookup_marks_the_kept_entries_that_share_a_name() -> None:
    read = read_options(_e1_options(), _E1["query"], request_terms=[])

    assert read.lookup is not None
    assert read.lookup.same_named == [["IPR050205", "IPR050236"]]


def _assay_tree() -> WDKVocabulary:
    body = load_recorded("search_genes_by_mass_spec").json_body()
    search = WDKSearchResponse.model_validate(body).search_data
    [assay] = [p for p in search.parameters or [] if p.name == "ms_assay"]
    assert assay.vocabulary is not None
    return assay.vocabulary


def test_entries_under_different_organisms_are_not_one_name() -> None:
    tree = _assay_tree()

    read = read_options(
        flatten_vocab(tree),
        ["female gametocytes"],
        request_terms=[],
        under=vocab_paths(tree),
    )

    assert read.lookup is not None
    assert read.lookup.same_named == []


def test_entries_no_parent_tells_apart_stay_one_name() -> None:
    read = read_options(
        _e1_options(), _E1["query"], request_terms=[], under=vocab_paths(None)
    )

    assert read.lookup is not None
    assert read.lookup.same_named == [["IPR050205", "IPR050236"]]


def test_a_path_names_the_labels_above_an_entry() -> None:
    paths = vocab_paths(_assay_tree())

    assert paths["female gametocytes_Plasmodium falciparum 3D7"] == (
        "<b>Plasmodium</b>",
        "<b>Plasmodium falciparum</b>",
        "<b>Plasmodium falciparum 3D7</b>",
        "Gametocyte proteomics (Lasonder et al.)",
    )
