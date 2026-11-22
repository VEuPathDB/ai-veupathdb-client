"""Parameter normalization on the way to the wire.

A profile pattern is a census pattern or it is nothing: the value is matched
with SQL LIKE against a colon-joined census, so any other shape matches nothing
and WDK answers 200 with a count. A clade code expands to the species the
census holds, and under ``countOnlyLeaves`` a branch term expands to its leaves.
"""

from __future__ import annotations

import json
from typing import cast

import pytest
from pydantic import JsonValue

from veupathdb.domain.parameters.phyletic import (
    canonical_census_pattern,
    read_census,
    validate_phyletic_codes,
)
from veupathdb.domain.parameters.wdk_vocab import FAKE_ALL_SENTINEL, WDKVocabTerm
from veupathdb.errors import VEuPathDBError
from veupathdb.json_types import JSONObject
from veupathdb.wdk.phyletic_tree import phyletic_tree_of
from veupathdb.wdk.tree_leaves import leaves_of_tree_values
from veupathdb.wdk.wdk_parameters import (
    WDKEnumParam,
    WDKParameter,
    WDKStringParam,
)

_KNOWN = {"cpar", "tgon", "pfal", "apicomplexa"}


def _term(code: str, display: str) -> WDKVocabTerm:
    return WDKVocabTerm((code, display, None))


_TREE_PARAMS: list[WDKParameter] = [
    WDKStringParam(name="profile_pattern", is_visible=False),
    WDKStringParam(name="included_species", allow_empty_value=True),
    WDKStringParam(name="excluded_species", allow_empty_value=True),
    WDKEnumParam(
        name="phyletic_term_map",
        type="multi-pick-vocabulary",
        vocabulary=[
            _term("ALL", "Root"),
            _term("EUKA", "Eukaryota"),
            _term("MAMM", "Mammalia"),
            _term("hsap", "Homo sapiens REF"),
            _term("mmus", "Mus musculus"),
            _term("pfal", "Plasmodium falciparum 3D7"),
        ],
    ),
    WDKEnumParam(
        name="phyletic_indent_map",
        type="multi-pick-vocabulary",
        vocabulary=[
            _term("EUKA", "1"),
            _term("MAMM", "2"),
            _term("hsap", "3"),
            _term("mmus", "3"),
            _term("pfal", "2"),
        ],
    ),
]

_LEAVES = ["17 Hour", "18 Hour", "19 Hour"]
_OTHER_LEAVES = ["24 Hour", "25 Hour"]


def _empty_indent_map() -> WDKParameter:
    return WDKEnumParam(
        name="phyletic_indent_map", type="multi-pick-vocabulary", vocabulary=[]
    )


_TREE = phyletic_tree_of(_TREE_PARAMS)


class TestACensusPatternIsRead:
    @pytest.mark.parametrize(
        ("pattern", "states"),
        [
            ("%", {}),
            ("%cpar:Y%", {"cpar": "include"}),
            ("%cpar:N%", {"cpar": "exclude"}),
            ("%hsap:N%", {"hsap": "exclude"}),
            ("%cpar:N%pfal:Y%", {"cpar": "exclude", "pfal": "include"}),
            ("%atum:Y%bant:Y%", {"atum": "include", "bant": "include"}),
            ("%pfal:Y%hsap:N%", {"pfal": "include", "hsap": "exclude"}),
        ],
    )
    def test_present_and_absent_tokens(
        self, pattern: str, states: dict[str, str]
    ) -> None:
        assert read_census(pattern).states == states


class TestAnythingElseIsRefused:
    @pytest.mark.parametrize(
        ("pattern", "repeated_code"),
        [
            ("%cpar:0%", None),
            ("%cpar:1T%", None),
            ("%cpar:y%", None),
            ("%cpar:%", None),
            ("%:Y%", None),
            # Valid in OrthoMCL's phyletic_expression grammar, not in this one.
            ("hsap=1T", None),
            ("hsap>=1T", None),
            ("hsap=0T", None),
            ("not a pattern at all", None),
            ("", None),
            ("%hsap=1T%", None),
            ("%hsap%", None),
            # The pattern is derived from the two species lists, which expand a
            # clade to its leaves; no producer writes a quantifier.
            ("%apicomplexa:Y:all%", None),
            # One species has one state in the census, so this matches nothing.
            ("%hsap:Y%hsap:N%", "hsap"),
        ],
    )
    def test_the_token_is_refused(
        self, pattern: str, repeated_code: str | None
    ) -> None:
        census = read_census(pattern)

        assert (census.states, census.repeated_code) == (None, repeated_code)


class TestTheCodeCheck:
    def test_an_unknown_code_is_rejected(self) -> None:
        with pytest.raises(VEuPathDBError) as err:
            validate_phyletic_codes(["zzzz"], _KNOWN)

        assert "zzzz" in str(err.value.detail)

    def test_the_error_is_a_validation_error(self) -> None:
        with pytest.raises(VEuPathDBError) as err:
            validate_phyletic_codes(["zzzz"], _KNOWN)

        assert err.value.status == 422

    def test_known_codes_pass(self) -> None:
        codes = ["cpar", "pfal", "apicomplexa"]

        assert set(codes) <= _KNOWN
        validate_phyletic_codes(codes, _KNOWN)


class TestTheProfilePatternExpansion:
    def test_a_clade_becomes_its_species(self) -> None:
        got = canonical_census_pattern("%MAMM:N%pfal:Y%", _TREE)

        assert got == "%hsap:N%mmus:N%pfal:Y%"

    def test_an_explicit_species_overrides_its_clade(self) -> None:
        got = canonical_census_pattern("%MAMM:N%hsap:Y%", _TREE)

        assert got == "%hsap:Y%mmus:N%"

    def test_species_codes_are_sorted_into_census_order(self) -> None:
        got = canonical_census_pattern("%pfal:Y%hsap:N%", _TREE)

        assert got == "%hsap:N%pfal:Y%"

    def test_the_bare_wildcard_stands(self) -> None:
        assert canonical_census_pattern("%", _TREE) == "%"

    def test_a_search_that_carries_no_tree_leaves_the_pattern_alone(self) -> None:
        got = canonical_census_pattern("%pfal:Y%", None)

        assert got == "%pfal:Y%"

    def test_an_unreadable_tree_ships_the_pattern_sorted_and_unexpanded(
        self,
    ) -> None:
        # Without the depths a clade holds no species, so expanding would drop
        # the constraint instead of widening it.
        flat = [
            p if p.name != "phyletic_indent_map" else _empty_indent_map()
            for p in _TREE_PARAMS
        ]

        got = canonical_census_pattern("%pfal:Y%MAMM:N%", phyletic_tree_of(flat))

        assert got == "%MAMM:N%pfal:Y%"


class TestTheProfilePatternGuard:
    def test_the_published_default_is_refused(self) -> None:
        with pytest.raises(VEuPathDBError) as err:
            canonical_census_pattern("hsap=1T", _TREE)

        assert err.value.status == 422

    def test_an_unknown_code_is_refused(self) -> None:
        with pytest.raises(VEuPathDBError) as err:
            canonical_census_pattern("%zzzz:Y%", _TREE)

        assert err.value.status == 422
        assert "zzzz" in str(err.value.detail)

    def test_a_repeated_code_is_named(self) -> None:
        with pytest.raises(VEuPathDBError) as err:
            canonical_census_pattern("%hsap:Y%hsap:N%", _TREE)

        assert err.value.status == 422
        assert "hsap" in str(err.value.detail)
        assert "census token" not in str(err.value.detail)


def _tree() -> JSONObject:
    return cast(
        "JSONObject",
        {
            "data": {"term": "@@fake@@", "display": "@@fake@@"},
            "children": [
                {
                    "data": {"term": "Trophozoite", "display": "17-30 Hours"},
                    "children": [
                        {
                            "data": {"term": "Early Trophozoite", "display": "17-23"},
                            "children": [
                                {"data": {"term": t, "display": t}} for t in _LEAVES
                            ],
                        },
                        {
                            "data": {"term": "Late Trophozoite", "display": "24-30"},
                            "children": [
                                {"data": {"term": t, "display": t}}
                                for t in _OTHER_LEAVES
                            ],
                        },
                    ],
                }
            ],
        },
    )


def _tree_param(*, count_only_leaves: bool = True) -> WDKParameter:
    raw: JSONObject = {
        "type": "multi-pick-vocabulary",
        "name": "samples",
        "display_name": "Samples",
        "display_type": "treeBox",
        "count_only_leaves": count_only_leaves,
        "vocabulary": cast("JsonValue", _tree()),
        "allow_empty_value": False,
    }
    return cast("WDKParameter", WDKEnumParam.model_validate(raw))


def _expand(value: list[str], *, count_only_leaves: bool = True) -> list[str]:
    result = leaves_of_tree_values(
        [_tree_param(count_only_leaves=count_only_leaves)],
        {"samples": json.dumps(value)},
        "GenesByProfile",
    )
    return list(json.loads(result["samples"]))


class TestABranchBecomesItsLeaves:
    def test_a_top_branch_expands_to_every_leaf_under_it(self) -> None:
        assert _expand(["Trophozoite"]) == [*_LEAVES, *_OTHER_LEAVES]

    def test_an_inner_branch_expands_to_its_own_leaves(self) -> None:
        assert _expand(["Early Trophozoite"]) == _LEAVES

    def test_two_branches_do_not_repeat_a_leaf(self) -> None:
        expanded = _expand(["Trophozoite", "Early Trophozoite"])

        assert expanded == [*_LEAVES, *_OTHER_LEAVES]

    def test_a_leaf_is_left_alone(self) -> None:
        assert _expand(["18 Hour"]) == ["18 Hour"]

    def test_a_branch_and_a_leaf_merge(self) -> None:
        assert _expand(["Late Trophozoite", "18 Hour"]) == [*_OTHER_LEAVES, "18 Hour"]


class TestWhatIsLeftUntouched:
    def test_a_param_that_counts_branches_is_not_expanded(self) -> None:
        assert _expand(["Trophozoite"], count_only_leaves=False) == ["Trophozoite"]

    def test_an_unknown_term_is_passed_through_for_wdk_to_judge(self) -> None:
        assert _expand(["99 Hour"]) == ["99 Hour"]

    def test_the_synthetic_root_does_not_select_the_whole_vocabulary(self) -> None:
        # It names no real term, so expanding it would turn a filter into a
        # criterion that removes nothing.
        assert _expand([FAKE_ALL_SENTINEL]) != [*_LEAVES, *_OTHER_LEAVES]

    def test_the_synthetic_root_is_left_for_wdk_to_refuse(self) -> None:
        assert _expand([FAKE_ALL_SENTINEL]) == [FAKE_ALL_SENTINEL]
