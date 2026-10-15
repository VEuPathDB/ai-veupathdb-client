"""OrthoMCL's phyletic pattern expression: its grammar, its codes and its reading."""

from __future__ import annotations

import pytest

from veupathdb.domain.parameters.phyletic import PhyleticTree, TaxonEntry
from veupathdb.domain.parameters.phyletic_expression import (
    PHYLETIC_EXPRESSION_PARAM,
    Combination,
    PhyleticExpression,
    TaxaCount,
    check_expression,
)
from veupathdb.errors import ValidationError

_STRAINS = ["pfag", "pfsg", "pfac", "pfad", "pfga"]


def _tree() -> PhyleticTree:
    return PhyleticTree.from_taxa(
        [
            TaxonEntry(id="1", parent_id=None, code="ALL", label="Root"),
            TaxonEntry(id="2", parent_id="1", code="EUKA", label="Eukaryota"),
            TaxonEntry(id="3", parent_id="2", code="HAEM", label="Haemosporida"),
            TaxonEntry(
                id="4", parent_id="3", code="pfal", label="Plasmodium falciparum 3D7"
            ),
            *(
                TaxonEntry(
                    id=f"s{code}",
                    parent_id="3",
                    code=code,
                    label=f"Plasmodium falciparum {code}",
                )
                for code in _STRAINS
            ),
        ]
    )


def test_a_unit_reads_its_codes_operator_and_count() -> None:
    parsed = PhyleticExpression.parse("hsap+ecol>=10")

    assert parsed.root == TaxaCount(
        codes=("hsap", "ecol"), op=">=", count=10, taxa=False
    )


def test_a_count_with_t_counts_taxa() -> None:
    parsed = PhyleticExpression.parse("EUKA=35T")

    assert parsed.root == TaxaCount(codes=("EUKA",), op="=", count=35, taxa=True)


def test_and_and_or_combine_units_and_parentheses_nest_them() -> None:
    parsed = PhyleticExpression.parse("(EUKA>=5T AND hsap>=10) OR pfal<20")

    assert parsed.root == Combination(
        join="OR",
        terms=(
            Combination(
                join="AND",
                terms=(
                    TaxaCount(codes=("EUKA",), op=">=", count=5, taxa=True),
                    TaxaCount(codes=("hsap",), op=">=", count=10, taxa=False),
                ),
            ),
            TaxaCount(codes=("pfal",), op="<", count=20, taxa=False),
        ),
    )


def test_the_written_form_is_the_sites_spelling() -> None:
    parsed = PhyleticExpression.parse("( EUKA >= 5t and hsap>=10 ) or pfal < 20")

    assert parsed.render() == "(EUKA>=5T AND hsap>=10) OR pfal<20"


def test_codes_are_listed_once_in_the_order_they_appear() -> None:
    parsed = PhyleticExpression.parse("pfal>=1T AND pfag+pfal+pfsg<=1T")

    assert parsed.codes() == ["pfal", "pfag", "pfsg"]


@pytest.mark.parametrize(
    ("text", "fault"),
    [
        ("", "is empty"),
        ("pfag+>=1", "'+' joins two codes"),
        ("pfal", "needs an operator and a count"),
        ("pfal>=", "needs an operator and a count"),
        ("pfal>=1 AND", "ends after AND"),
        ("(pfal>=1", "a '(' is never closed"),
        ("pfal>=1)", "a ')' closes nothing"),
        ("pfal>=1 pfag>=1", "AND or OR joins two units"),
    ],
)
def test_a_malformed_expression_is_refused_on_its_parameter(
    text: str, fault: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        PhyleticExpression.parse(text)

    assert fault in caught.value.detail
    assert PHYLETIC_EXPRESSION_PARAM in str(caught.value.errors)


def test_and_beside_or_without_parentheses_is_refused() -> None:
    with pytest.raises(ValidationError) as caught:
        PhyleticExpression.parse("pfal>=1T AND pfag>=1T OR pfsg>=1T")

    assert "parentheses" in caught.value.detail


def test_a_code_the_taxonomy_carries_passes_and_all_is_the_whole_tree() -> None:
    check_expression(
        PhyleticExpression.parse("pfal>=1T AND HAEM<=2T AND ALL>=3T"), _tree()
    )


def test_a_code_the_taxonomy_lacks_is_refused_by_name() -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse("pfal>=1T AND zzzz=0T"), _tree())

    assert "zzzz" in caught.value.detail
    assert PHYLETIC_EXPRESSION_PARAM in str(caught.value.errors)


def test_a_panel_absent_from_at_least_two_reads_as_a_ceiling_on_its_taxa() -> None:
    panel = "+".join(_STRAINS)
    parsed = PhyleticExpression.parse(f"pfal>=1T AND {panel}<=3T")

    assert parsed.describe(_tree()) == (
        "at least 1 taxon of Plasmodium falciparum 3D7 and at most 3 taxa of "
        "these 5: Plasmodium falciparum pfag, Plasmodium falciparum pfsg, Plasmodium "
        "falciparum pfac, Plasmodium falciparum pfad, Plasmodium falciparum pfga"
    )


def test_a_nested_group_reads_in_parentheses_and_counts_sequences() -> None:
    parsed = PhyleticExpression.parse("(pfal=1 OR pfag>2) AND HAEM<4T")

    assert parsed.describe(_tree()) == (
        "(exactly 1 sequence of Plasmodium falciparum 3D7 or more than 2 "
        "sequences of Plasmodium falciparum pfag) and fewer than 4 taxa of "
        "Haemosporida"
    )


@pytest.mark.parametrize(
    "unit",
    [
        "pfag+pfsg+pfac<=3T",
        "pfag+pfsg+pfac<4T",
        "HAEM>=0T",
        "pfag+pfsg>2T",
        "pfag+pfsg=3T",
        "ALL>=7T",
    ],
)
def test_a_unit_every_group_meets_or_none_can_is_refused(unit: str) -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse(f"pfal>=1T AND {unit}"), _tree())

    assert "states no constraint" in caught.value.detail
    assert PHYLETIC_EXPRESSION_PARAM in str(caught.value.errors)


def test_the_refusal_names_how_many_taxa_the_unit_spans() -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse("pfag+pfsg+pfac<=3T"), _tree())

    assert "3 taxa" in caught.value.detail


@pytest.mark.parametrize(
    "unit", ["pfag+pfsg+pfac<=1T", "HAEM<=5T", "HAEM=6T", "pfal>=1T", "pfal>=1"]
)
def test_a_unit_that_divides_the_groups_passes(unit: str) -> None:
    check_expression(PhyleticExpression.parse(unit), _tree())
