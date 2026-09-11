"""The phyletic tree, the census pattern, and the documentation lists."""

from __future__ import annotations

import pytest

from veupathdb.domain.parameters.phyletic import (
    PHYLETIC_LIST_PARAMS,
    PHYLETIC_MAP_PARAMS,
    PHYLETIC_PARAM_NAMES,
    PhyleticBinding,
    PhyleticTree,
    PhyleticUnresolved,
    census_states,
    derive_binding,
    encode_profile_pattern,
    species_lists,
    validate_phyletic_codes,
)
from veupathdb.domain.parameters.wdk_vocab import WDKVocabTerm
from veupathdb.errors import ValidationError


def _term(code: str, display: str) -> WDKVocabTerm:
    return WDKVocabTerm((code, display, None))


TERMS = [
    _term("ALL", "Root"),
    _term("EUKA", "Eukaryota"),
    _term("MAMM", "Mammalia"),
    _term("hsap", "Homo sapiens REF"),
    _term("mmus", "Mus musculus"),
    _term("pfal", "Plasmodium falciparum 3D7"),
    _term("BACT", "Bacteria"),
    _term("ecol", "Escherichia coli"),
]
INDENTS = [
    _term("EUKA", "1"),
    _term("MAMM", "2"),
    _term("hsap", "3"),
    _term("mmus", "3"),
    _term("pfal", "2"),
    _term("BACT", "1"),
    _term("ecol", "2"),
]


def _tree() -> PhyleticTree:
    return PhyleticTree.from_vocab(TERMS, INDENTS)


class TestTheParamNames:
    def test_the_five_names_of_a_phyletic_search(self) -> None:
        expected = {
            "profile_pattern",
            "included_species",
            "excluded_species",
            "phyletic_indent_map",
            "phyletic_term_map",
        }
        assert set(PHYLETIC_PARAM_NAMES) == expected

    def test_the_two_visible_lists_a_caller_writes(self) -> None:
        assert set(PHYLETIC_LIST_PARAMS) == {"included_species", "excluded_species"}

    def test_the_lists_are_the_binding_without_the_derived_pattern(self) -> None:
        fields = set(PhyleticBinding.model_fields)

        assert fields - PHYLETIC_LIST_PARAMS == {"profile_pattern"}

    def test_the_five_names_are_the_maps_the_lists_and_the_pattern(self) -> None:
        parts = PHYLETIC_MAP_PARAMS | PHYLETIC_LIST_PARAMS | {"profile_pattern"}

        assert parts == PHYLETIC_PARAM_NAMES
        assert not PHYLETIC_MAP_PARAMS & PHYLETIC_LIST_PARAMS


class TestTheTree:
    def test_builds_the_hierarchy(self) -> None:
        roots = _tree().roots
        assert [r.code for r in roots] == ["EUKA", "BACT"]
        assert [c.code for c in roots[0].children] == ["MAMM", "pfal"]
        assert [c.code for c in roots[0].children[0].children] == ["hsap", "mmus"]

    def test_empty_vocab_is_an_empty_tree(self) -> None:
        assert PhyleticTree.from_vocab([], []).roots == []

    def test_a_code_missing_from_the_indent_map_is_a_root(self) -> None:
        tree = PhyleticTree.from_vocab([_term("zzzz", "Unplaced")], [])
        assert [r.code for r in tree.roots] == ["zzzz"]
        assert tree.roots[0].depth == 1

    def test_labels_exclude_the_root(self) -> None:
        assert [o.value for o in _tree().labels()][:2] == ["EUKA", "MAMM"]
        assert all(o.value != "ALL" for o in _tree().labels())

    def test_labels_carry_the_display_name(self) -> None:
        labels = {o.value: o.display for o in _tree().labels()}
        assert labels["pfal"] == "Plasmodium falciparum 3D7"


class TestResolvingTerms:
    def test_a_code_a_label_and_a_comma_list(self) -> None:
        got = _tree().resolve_terms("pfal, Homo sapiens REF")
        assert got.codes == ["pfal", "hsap"]
        assert got.unknown == []

    def test_labels_are_case_insensitive_and_lists_are_read(self) -> None:
        assert _tree().resolve_terms(["mammalia", "PFAL"]).codes == ["MAMM", "pfal"]

    def test_the_empty_marker_and_blank_are_nothing(self) -> None:
        assert _tree().resolve_terms("n/a").codes == []
        assert _tree().resolve_terms("").codes == []
        assert _tree().resolve_terms([]).codes == []

    def test_a_repeated_term_is_kept_once(self) -> None:
        assert _tree().resolve_terms("pfal, Plasmodium falciparum 3D7").codes == [
            "pfal"
        ]

    def test_unknown_names_are_reported_not_dropped(self) -> None:
        got = _tree().resolve_terms("pfal, Plasmodium falciparum, hsap")
        assert got.codes == ["pfal", "hsap"]
        assert got.unknown == ["Plasmodium falciparum"]

    def test_a_repeated_unknown_is_reported_once(self) -> None:
        got = _tree().resolve_terms("Nosema, Nosema")
        assert got.unknown == ["Nosema"]

    def test_the_root_is_not_resolvable(self) -> None:
        got = _tree().resolve_terms("ALL, All Organisms")
        assert got.codes == []
        assert got.unknown == ["ALL", "All Organisms"]


class TestLeafStates:
    def test_a_clade_becomes_its_leaves(self) -> None:
        assert _tree().leaf_states([], ["MAMM"]) == {
            "hsap": "exclude",
            "mmus": "exclude",
        }

    def test_an_explicit_leaf_wins_over_its_clade(self) -> None:
        assert _tree().leaf_states(["hsap"], ["MAMM"]) == {
            "hsap": "include",
            "mmus": "exclude",
        }

    def test_a_species_is_left_alone(self) -> None:
        assert _tree().leaf_states(["pfal"], []) == {"pfal": "include"}

    def test_nothing_selected_constrains_nothing(self) -> None:
        assert _tree().leaf_states([], []) == {}


class TestThePattern:
    def test_wraps_and_separates_with_the_wildcard(self) -> None:
        assert (
            encode_profile_pattern({"hsap": "exclude", "pfal": "include"})
            == "%hsap:N%pfal:Y%"
        )

    def test_sorts_into_ascending_code_order(self) -> None:
        assert encode_profile_pattern({"yepe": "include", "wsuc": "include"}) == (
            "%wsuc:Y%yepe:Y%"
        )

    def test_the_other_measured_ordering_pairs(self) -> None:
        assert encode_profile_pattern({"bant": "include", "atum": "include"}) == (
            "%atum:Y%bant:Y%"
        )
        assert encode_profile_pattern({"hsap": "include", "atum": "include"}) == (
            "%atum:Y%hsap:Y%"
        )

    def test_no_constraint_is_a_bare_wildcard(self) -> None:
        assert encode_profile_pattern({}) == "%"


class TestTheLists:
    def test_highest_nodes_comma_joined(self) -> None:
        assert species_lists(["pfal"], ["MAMM"]) == ("pfal", "MAMM")

    def test_several_codes_join_the_way_the_reference_client_reads_them(self) -> None:
        assert species_lists(["APIC"], ["BACT", "ARCH", "META"]) == (
            "APIC",
            "BACT, ARCH, META",
        )

    def test_empty_is_the_reference_marker(self) -> None:
        assert species_lists([], []) == ("n/a", "n/a")


class TestDeriveBinding:
    def test_the_gold_shape(self) -> None:
        binding = derive_binding(_tree(), "Plasmodium falciparum 3D7", "hsap")
        assert isinstance(binding, PhyleticBinding)
        assert binding.profile_pattern == "%hsap:N%pfal:Y%"
        assert (binding.included_species, binding.excluded_species) == ("pfal", "hsap")

    def test_a_clade_expands_in_the_pattern_and_stays_a_code_in_the_list(self) -> None:
        binding = derive_binding(_tree(), ["pfal"], ["Mammalia"])
        assert isinstance(binding, PhyleticBinding)
        assert binding.profile_pattern == "%hsap:N%mmus:N%pfal:Y%"
        assert binding.excluded_species == "MAMM"

    def test_nothing_selected_is_the_bare_wildcard_and_two_markers(self) -> None:
        binding = derive_binding(_tree(), "n/a", "n/a")
        assert isinstance(binding, PhyleticBinding)
        assert binding.profile_pattern == "%"
        assert (binding.included_species, binding.excluded_species) == ("n/a", "n/a")

    def test_unknown_terms_come_back_instead_of_a_binding(self) -> None:
        got = derive_binding(_tree(), "Plasmodium falciparum", "hsap")
        assert isinstance(got, PhyleticUnresolved)
        assert got.included_unknown == ["Plasmodium falciparum"]
        assert got.excluded_unknown == []
        assert got.conflicts == []

    def test_an_unknown_in_the_excluded_list_is_named_there(self) -> None:
        got = derive_binding(_tree(), "pfal", "Nosema, hsap")
        assert isinstance(got, PhyleticUnresolved)
        assert got.included_unknown == []
        assert got.excluded_unknown == ["Nosema"]

    def test_a_repeated_unknown_is_reported_once(self) -> None:
        got = derive_binding(_tree(), "Nosema, Nosema", "hsap")
        assert isinstance(got, PhyleticUnresolved)
        assert got.included_unknown == ["Nosema"]

    def test_a_code_in_both_lists_is_a_conflict_and_binds_nothing(self) -> None:
        got = derive_binding(_tree(), "pfal, hsap", "Homo sapiens REF")
        assert isinstance(got, PhyleticUnresolved)
        assert got.conflicts == ["hsap"]
        assert (got.included_unknown, got.excluded_unknown) == ([], [])


# The head of ``GenesByOrthologPattern``'s phyletic vocabularies, whose entries
# carry a parent term in the third element.
_PARENTED_TERMS: list[list[str | None]] = [
    ["BACT", "Bacteria", None],
    ["FIRM", "Firmicutes", "BACT"],
    ["bant", "Bacillus anthracis", "FIRM"],
    ["bsub", "Bacillus subtilis subsp. subtilis str. 168", "FIRM"],
    ["EUKA", "Eukaryota", None],
    ["MAMM", "Mammalia", "EUKA"],
    ["hsap", "Homo sapiens REF", "MAMM"],
]

_PARENTED_INDENTS: list[list[str | None]] = [
    ["BACT", "1", None],
    ["FIRM", "2", "BACT"],
    ["bant", "3", "FIRM"],
    ["bsub", "3", "FIRM"],
    ["EUKA", "1", None],
    ["MAMM", "2", "EUKA"],
    ["hsap", "3", "MAMM"],
]


class TestTheTreeIsBuiltFromTheParentTerm:
    def _tree(self) -> PhyleticTree:
        return PhyleticTree.from_vocab(
            [WDKVocabTerm(tuple(row)) for row in _PARENTED_TERMS],
            [WDKVocabTerm(tuple(row)) for row in _PARENTED_INDENTS],
        )

    def test_the_roots_are_the_entries_with_no_parent(self) -> None:
        assert [node.code for node in self._tree().roots] == ["BACT", "EUKA"]

    def test_a_clade_expands_to_the_species_under_it(self) -> None:
        states = self._tree().leaf_states(included=["FIRM"], excluded=["MAMM"])

        assert states == {"bant": "include", "bsub": "include", "hsap": "exclude"}

    def test_an_absent_indent_map_keeps_the_parent_structure(self) -> None:
        tree = PhyleticTree.from_vocab(
            [WDKVocabTerm(tuple(row)) for row in _PARENTED_TERMS], []
        )

        assert [node.code for node in tree.roots] == ["BACT", "EUKA"]
        assert tree.leaf_states(included=["EUKA"], excluded=[]) == {"hsap": "include"}


class TestARefusalNamesTheParameter:
    """Both phyletic refusals carry the row shape the agent tools read."""

    def test_a_pattern_that_is_not_a_census_names_profile_pattern(self) -> None:
        with pytest.raises(ValidationError) as err:
            census_states("Plasmodium falciparum AND NOT Homo sapiens")

        assert err.value.errors == [
            {
                "param": "profile_pattern",
                "messages": [
                    (
                        "'Plasmodium falciparum AND NOT Homo sapiens' is not built "
                        "from census tokens."
                    )
                ],
            }
        ]

    def test_a_repeated_code_names_profile_pattern(self) -> None:
        with pytest.raises(ValidationError) as err:
            census_states("%hsap:Y%hsap:N%")

        assert err.value.errors == [
            {
                "param": "profile_pattern",
                "messages": ["'hsap' appears twice in '%hsap:Y%hsap:N%'."],
            }
        ]

    def test_an_unknown_code_names_profile_pattern(self) -> None:
        with pytest.raises(ValidationError) as err:
            validate_phyletic_codes(["zzzz", "pfal"], {"pfal"})

        assert err.value.errors == [
            {"param": "profile_pattern", "messages": ["Unknown codes: zzzz."]}
        ]

    def test_the_detail_still_carries_the_repair(self) -> None:
        with pytest.raises(ValidationError) as err:
            census_states("nonsense")

        assert "lookup_phyletic_codes()" in str(err.value.detail)
