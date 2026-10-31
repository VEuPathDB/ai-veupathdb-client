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
            TaxonEntry(id="1", parent_id=None, code="ALL", label="Root", clade=True),
            TaxonEntry(
                id="2", parent_id="1", code="EUKA", label="Eukaryota", clade=True
            ),
            TaxonEntry(
                id="3", parent_id="2", code="HAEM", label="Haemosporida", clade=True
            ),
            TaxonEntry(
                id="4",
                parent_id="3",
                code="pfal",
                label="Plasmodium falciparum 3D7",
                clade=False,
            ),
            *(
                TaxonEntry(
                    id=f"s{code}",
                    parent_id="3",
                    code=code,
                    label=f"Plasmodium falciparum {code}",
                    clade=False,
                )
                for code in _STRAINS
            ),
            TaxonEntry(
                id="5", parent_id="2", code="TOXO", label="Toxoplasma", clade=True
            ),
            TaxonEntry(
                id="6",
                parent_id="5",
                code="tgon",
                label="Toxoplasma gondii ME49",
                clade=False,
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

    assert fault in (caught.value.detail or "")
    assert PHYLETIC_EXPRESSION_PARAM in str(caught.value.errors)


def test_and_binds_before_or_without_parentheses() -> None:
    parsed = PhyleticExpression.parse("pfal>=1T AND pfag>=1T OR pfsg>=1T")

    assert parsed.root == Combination(
        join="OR",
        terms=(
            Combination(
                join="AND",
                terms=(
                    TaxaCount(codes=("pfal",), op=">=", count=1, taxa=True),
                    TaxaCount(codes=("pfag",), op=">=", count=1, taxa=True),
                ),
            ),
            TaxaCount(codes=("pfsg",), op=">=", count=1, taxa=True),
        ),
    )


def test_parentheses_around_one_join_parse_as_one_list() -> None:
    assert (
        PhyleticExpression.parse("(pfal>=1T OR pfag>=1T) OR pfsg>=1T")
        == PhyleticExpression.parse("pfal>=1T OR pfag>=1T OR pfsg>=1T")
        == PhyleticExpression.parse("pfal>=1T OR (pfag>=1T OR pfsg>=1T)")
    )


_CEILING = "pfag+pfsg<=1T"
_NONE = "pfag+pfsg=0T"


def test_an_or_of_and_terms_parses_to_one_tree_with_or_without_parentheses() -> None:
    wrapped = PhyleticExpression.parse(
        f"(pfal>=1T AND {_CEILING}) OR (pfal>=1T AND {_NONE})"
    )
    bare = PhyleticExpression.parse(f"pfal>=1T AND {_CEILING} OR pfal>=1T AND {_NONE}")

    assert wrapped == bare
    check_expression(wrapped, _tree())


def test_parentheses_the_site_drops_are_refused_with_its_reading() -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(
            PhyleticExpression.parse(f"pfal>=1T AND ({_CEILING} OR {_NONE})"), _tree()
        )

    assert f"it reads (pfal>=1T AND {_CEILING}) OR {_NONE}" in (
        caught.value.detail or ""
    )
    assert (
        "the site drops parentheses and reads AND before OR; write an OR of AND "
        "terms, repeating shared units in each term" in (caught.value.detail or "")
    )
    assert PHYLETIC_EXPRESSION_PARAM in str(caught.value.errors)


@pytest.mark.parametrize("unit", ["TOXO<=0T", "TOXO<1T", "TOXO<=0", "TOXO<1"])
def test_an_upper_bound_of_zero_is_refused_naming_the_form_for_absence(
    unit: str,
) -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse(f"pfal>=1T AND {unit}"), _tree())

    assert f"{unit} matches no group" in (caught.value.detail or "")
    assert "write TOXO=0T for absence" in (caught.value.detail or "")


def test_an_upper_bound_is_false_on_a_group_with_no_protein_under_its_codes() -> None:
    group = {"pfal": 1}

    assert not PhyleticExpression.parse("TOXO<=0T").holds_for(group, _tree())
    assert not PhyleticExpression.parse("TOXO<1T").holds_for(group, _tree())
    assert not PhyleticExpression.parse("TOXO<=3").holds_for(group, _tree())
    assert not PhyleticExpression.parse("TOXO>=0T").holds_for(group, _tree())
    assert not PhyleticExpression.parse("TOXO=1T").holds_for(group, _tree())
    assert not PhyleticExpression.parse("TOXO=2").holds_for(group, _tree())
    assert not PhyleticExpression.parse("TOXO>0T").holds_for(group, _tree())
    assert not PhyleticExpression.parse("TOXO>=1").holds_for(group, _tree())


def test_a_count_of_exactly_zero_is_absence() -> None:
    assert PhyleticExpression.parse("TOXO=0T").holds_for({"pfal": 1}, _tree())
    assert PhyleticExpression.parse("TOXO=0").holds_for({"pfal": 1}, _tree())
    assert not PhyleticExpression.parse("TOXO=0T").holds_for({"tgon": 2}, _tree())


_PANEL = "+".join(_STRAINS)


def test_at_most_n_including_none_is_an_or_of_two_and_terms() -> None:
    alone, beside = {"pfal": 1}, {"pfal": 1, "pfag": 2}
    ceiling = PhyleticExpression.parse(f"pfal>=1T AND {_PANEL}<=3T")
    with_none = PhyleticExpression.parse(
        f"pfal>=1T AND {_PANEL}=0T OR pfal>=1T AND {_PANEL}<=3T"
    )

    assert not ceiling.holds_for(alone, _tree())
    assert with_none.holds_for(alone, _tree())
    assert ceiling.holds_for(beside, _tree())
    assert with_none.holds_for(beside, _tree())


def test_a_genome_count_counts_genomes_that_hold_a_protein() -> None:
    group = {"pfal": 3, "pfag": 1, "pfsg": 0, "tgon": 2}

    assert PhyleticExpression.parse("HAEM=2T AND HAEM=4").holds_for(group, _tree())
    assert PhyleticExpression.parse("ALL=3T AND ALL=6").holds_for(group, _tree())
    assert not PhyleticExpression.parse("HAEM>2T").holds_for(group, _tree())


def test_a_code_the_taxonomy_carries_passes_and_all_is_the_whole_tree() -> None:
    check_expression(
        PhyleticExpression.parse("pfal>=1T AND HAEM<=2T AND ALL>=3T"), _tree()
    )


def test_a_code_the_taxonomy_lacks_is_refused_by_name() -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse("pfal>=1T AND zzzz=0T"), _tree())

    assert "zzzz" in (caught.value.detail or "")
    assert PHYLETIC_EXPRESSION_PARAM in str(caught.value.errors)


def test_a_panel_absent_from_at_least_two_reads_as_a_ceiling_on_its_taxa() -> None:
    panel = "+".join(_STRAINS)
    parsed = PhyleticExpression.parse(f"pfal>=1T AND {panel}<=3T")

    assert parsed.describe(_tree()) == (
        "at least 1 genome of Plasmodium falciparum 3D7 and at most 3 genomes of "
        "these 5: Plasmodium falciparum pfag, Plasmodium falciparum pfsg, Plasmodium "
        "falciparum pfac, Plasmodium falciparum pfad, Plasmodium falciparum pfga "
        "(5 genomes of 1 species; Plasmodium falciparum 5)"
    )


def test_a_nested_group_reads_in_parentheses_and_counts_sequences() -> None:
    parsed = PhyleticExpression.parse("(pfal=1 OR pfag>2) AND HAEM<4T")

    assert parsed.describe(_tree()) == (
        "(exactly 1 protein of Plasmodium falciparum 3D7 or more than 2 "
        "proteins of Plasmodium falciparum pfag) and fewer than 4 genomes of "
        "Haemosporida (6 genomes of 1 species; Plasmodium falciparum 6)"
    )


def test_a_unit_over_one_genome_per_species_names_only_the_counts() -> None:
    parsed = PhyleticExpression.parse("pfal+tgon>=1T")

    assert parsed.describe(_tree()) == (
        "at least 1 genome of these 2: Plasmodium falciparum 3D7, Toxoplasma "
        "gondii ME49 (2 genomes of 2 species)"
    )


def test_a_clade_unit_names_its_species_of_two_or_more_genomes() -> None:
    parsed = PhyleticExpression.parse("EUKA>=2T")

    assert parsed.describe(_tree()) == (
        "at least 2 genomes of Eukaryota (7 genomes of 2 species; "
        "Plasmodium falciparum 6)"
    )


def test_units_over_one_set_name_its_breakdown_once_in_any_spelling() -> None:
    parsed = PhyleticExpression.parse(
        "HAEM>=2T AND pfal+pfag+pfsg+pfac+pfad+pfga<=5T OR HAEM=0T"
    )

    assert parsed.describe(_tree()) == (
        "(at least 2 genomes of Haemosporida (6 genomes of 1 species; Plasmodium "
        "falciparum 6) and at most 5 genomes of these 6: Plasmodium falciparum "
        "3D7, Plasmodium falciparum pfag, Plasmodium falciparum pfsg, Plasmodium "
        "falciparum pfac, Plasmodium falciparum pfad, Plasmodium falciparum pfga) "
        "or exactly 0 genomes of Haemosporida"
    )


def test_units_over_different_sets_each_name_their_breakdown() -> None:
    parsed = PhyleticExpression.parse("EUKA>=2T AND HAEM<=5T")

    assert parsed.describe(_tree()) == (
        "at least 2 genomes of Eukaryota (7 genomes of 2 species; Plasmodium "
        "falciparum 6) and at most 5 genomes of Haemosporida (6 genomes of 1 "
        "species; Plasmodium falciparum 6)"
    )


@pytest.mark.parametrize(
    "unit",
    [
        "pfag+pfsg+pfac<=3T",
        "pfag+pfsg+pfac<4T",
        "HAEM>=0T",
        "pfag+pfsg>2T",
        "pfag+pfsg=3T",
        "ALL>=8T",
    ],
)
def test_a_unit_every_group_meets_or_none_can_is_refused(unit: str) -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse(f"pfal>=1T AND {unit}"), _tree())

    assert "states no constraint" in (caught.value.detail or "")
    assert PHYLETIC_EXPRESSION_PARAM in str(caught.value.errors)


def test_a_ceiling_over_every_genome_it_spans_reads_as_presence() -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse("pfag+pfsg+pfac<=3T"), _tree())

    assert (
        "pfag+pfsg+pfac<=3T over 3 genomes holds exactly the groups with a protein "
        "of its codes, so it states no constraint beyond pfag+pfsg+pfac>=1T"
    ) in (caught.value.detail or "")


def test_at_least_zero_proteins_reads_as_presence() -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse("pfal>=0"), _tree())

    assert "states no constraint beyond pfal>=1." in (caught.value.detail or "")


def test_the_refusal_names_one_genome_in_the_singular() -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse("pfal>=2T"), _tree())

    assert "pfal>=2T over 1 genome is true" in (caught.value.detail or "")


@pytest.mark.parametrize(
    "unit",
    [
        "pfag+pfsg+pfac<=1T",
        "pfag+pfsg+pfac<3T",
        "HAEM<=5T",
        "HAEM=6T",
        "pfal>=1T",
        "pfal>=1",
    ],
)
def test_a_unit_that_divides_the_groups_passes(unit: str) -> None:
    check_expression(PhyleticExpression.parse(unit), _tree())


def test_species_of_one_size_are_listed_by_name_after_larger_ones() -> None:
    genomes = [
        ("tga", "Toxoplasma gondii A"),
        ("tgb", "Toxoplasma gondii B"),
        ("eta", "Eimeria tenella A"),
        ("etb", "Eimeria tenella B"),
        ("nca", "Neospora caninum A"),
        ("ncb", "Neospora caninum B"),
        ("ncc", "Neospora caninum C"),
    ]
    tree = PhyleticTree.from_taxa(
        [
            TaxonEntry(
                id="1", parent_id=None, code="COCC", label="Coccidia", clade=True
            ),
            *(
                TaxonEntry(id=code, parent_id="1", code=code, label=label, clade=False)
                for code, label in genomes
            ),
        ]
    )

    assert PhyleticExpression.parse("COCC>=1T").describe(tree) == (
        "at least 1 genome of Coccidia (7 genomes of 3 species; "
        "Neospora caninum 3, Eimeria tenella 2, Toxoplasma gondii 2)"
    )


@pytest.mark.parametrize(
    ("unit", "named"),
    [
        ("pfal+HAEM>=1T", "pfal"),
        ("pfag+pfag>=1", "pfag"),
        ("HAEM+HAEM>=2T", "HAEM"),
        ("HAEM+EUKA>=2T", "pfac, pfad, pfag, pfal, pfga, pfsg"),
    ],
)
def test_a_unit_naming_a_genome_twice_is_refused(unit: str, named: str) -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse(unit), _tree())

    assert f"{unit} names these codes more than once: {named}" in (
        caught.value.detail or ""
    )
    assert "name each genome once" in (caught.value.detail or "")


@pytest.mark.parametrize("unit", ["pfal+HAEM=1T", "pfag+pfag>=1"])
def test_a_unit_naming_a_genome_twice_is_not_evaluated(unit: str) -> None:
    with pytest.raises(ValidationError) as caught:
        PhyleticExpression.parse(f"tgon>=1T OR {unit}").holds_for(
            {"pfal": 1, "pfag": 1}, _tree()
        )

    assert "name each genome once" in (caught.value.detail or "")
