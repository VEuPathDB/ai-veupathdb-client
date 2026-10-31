"""OrthoMCL's recorded taxonomy read as genomes, clades and species, and the
recorded groups of an expression read against it."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from veupathdb.domain.parameters import (
    PhyleticExpression,
    PhyleticTree,
    check_expression,
)
from veupathdb.errors import ValidationError
from veupathdb.testing.wdk_fixtures import fixture_request, load_recorded
from veupathdb.wdk.phyletic_tree import ortho_taxonomy_of
from veupathdb.wdk.wdk_models import WDKAnswer


def _recorded_tree() -> PhyleticTree:
    tree = ortho_taxonomy_of(
        WDKAnswer.model_validate(load_recorded("orthomcl_taxonomy").body)
    )
    assert tree is not None
    return tree


class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore")

    abbrev: str
    count: int


_ROWS = TypeAdapter(list[_Row])


class _Parameters(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phyletic_expression: str


class _SearchConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parameters: _Parameters


class _Asked(BaseModel):
    model_config = ConfigDict(extra="ignore")

    search_config: _SearchConfig = Field(alias="searchConfig")


def _asked(name: str) -> PhyleticExpression:
    asked = _Asked.model_validate(fixture_request(name).body)
    return PhyleticExpression.parse(asked.search_config.parameters.phyletic_expression)


def _groups(name: str = "orthomcl_group_taxon_counts") -> dict[str, dict[str, int]]:
    answer = WDKAnswer.model_validate(load_recorded(name).body)
    return {
        record.id[0].value: {
            row.abbrev: row.count
            for row in _ROWS.validate_python(record.tables["TaxonCounts"])
        }
        for record in answer.records
    }


def _labelled(tree: PhyleticTree, prefix: str) -> list[str]:
    return [n.code for n in tree.nodes() if not n.clade and n.label.startswith(prefix)]


@pytest.mark.parametrize(
    ("code", "genomes"),
    [
        ("ALL", 857),
        ("EUKA", 783),
        ("OEUK", 53),
        ("VIRI", 14),
        ("BACI", 0),
        ("APIC", 139),
        ("ACON", 80),
        ("HAEM", 63),
        ("PIRO", 17),
        ("COCC", 56),
        ("CRYP", 1),
        ("MAMM", 18),
        ("ARCH", 27),
        ("BACT", 47),
    ],
)
def test_a_code_counts_the_genomes_the_site_holds_under_it(
    code: str, genomes: int
) -> None:
    assert len(_recorded_tree().genomes_under([code])) == genomes


def test_an_empty_clade_is_a_clade_and_no_genome() -> None:
    baci = next(n for n in _recorded_tree().nodes() if n.code == "BACI")
    assert baci.clade
    assert baci.children == []


def test_the_plasmodium_genomes_group_into_23_species() -> None:
    tree = _recorded_tree()
    codes = _labelled(tree, "Plasmodium ")
    sizes = {g.species: len(g.genomes) for g in tree.species_groups(codes)}
    assert len(codes) == 61
    assert len(sizes) == 23
    assert sizes["Plasmodium falciparum"] == 20
    assert (
        sizes["Plasmodium vinckei"],
        sizes["Plasmodium vivax"],
        sizes["Plasmodium knowlesi"],
    ) == (7, 4, 3)
    assert sizes["Plasmodium ovale"] == 2
    assert sum(1 for n in sizes.values() if n == 1) == 13


def test_the_cryptosporidium_genomes_group_into_12_species() -> None:
    tree = _recorded_tree()
    codes = _labelled(tree, "Cryptosporidium ")
    sizes = {g.species: len(g.genomes) for g in tree.species_groups(codes)}
    assert len(codes) == 18
    assert len(sizes) == 12
    assert sizes["Cryptosporidium sp. 43IA8"] == 1
    assert sizes["Cryptosporidium sp. chipmunk"] == 1


def test_two_undescribed_leishmania_genomes_are_two_species() -> None:
    tree = _recorded_tree()
    groups = tree.species_groups(_labelled(tree, "Leishmania sp. "))
    assert [(g.species, g.genomes) for g in groups] == [
        ("Leishmania sp. Ghana", ("lspg",)),
        ("Leishmania sp. Namibia", ("lspn",)),
    ]


def test_toxoplasma_is_one_species_of_15_genomes() -> None:
    tree = _recorded_tree()
    groups = tree.species_groups(_labelled(tree, "Toxoplasma "))
    assert [(g.species, len(g.genomes)) for g in groups] == [("Toxoplasma gondii", 15)]


def test_a_unit_over_strains_names_its_genomes_and_species() -> None:
    tree = _recorded_tree()
    text = PhyleticExpression.parse(
        f"{'+'.join(_labelled(tree, 'Plasmodium '))}=61T"
    ).describe(tree)
    assert text.startswith("exactly 61 genomes of these 61: ")
    assert (
        "(61 genomes of 23 species; Plasmodium falciparum 20, Plasmodium vinckei 7, "
        "Plasmodium vivax 4, Plasmodium yoelii 4, Plasmodium knowlesi 3, " in text
    )


def test_two_units_over_one_clade_name_its_breakdown_once() -> None:
    tree = _recorded_tree()
    text = PhyleticExpression.parse("APIC>=139T AND APIC=139").describe(tree)
    alone = PhyleticExpression.parse("APIC>=139T").describe(tree)
    breakdown = alone.removeprefix("at least 139 genomes of Apicomplexa")
    assert breakdown.startswith(" (")
    assert text == (
        f"at least 139 genomes of Apicomplexa{breakdown} and exactly 139 "
        "proteins of Apicomplexa"
    )


def test_a_unit_over_an_empty_clade_is_refused() -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse("BACI>=1T"), _recorded_tree())

    assert "BACI>=1T over 0 genomes is true of every group or of none" in (
        caught.value.detail or ""
    )


def test_a_unit_over_an_empty_clade_with_a_count_of_zero_is_refused() -> None:
    with pytest.raises(ValidationError) as caught:
        check_expression(PhyleticExpression.parse("BACI=0T"), _recorded_tree())

    assert "BACI=0T over 0 genomes is true of every group" in (
        caught.value.detail or ""
    )


def test_both_measured_groups_hold_one_protein_in_every_apicomplexan_genome() -> None:
    tree, groups = _recorded_tree(), _groups()
    single = PhyleticExpression.parse("APIC=139T AND APIC=139")
    assert single.holds_for(groups["OG8_0031041"], tree)
    assert single.holds_for(groups["OG8_0003303"], tree)


def test_a_genome_count_counts_genomes_and_a_bare_count_sums_proteins() -> None:
    tree, proteins = _recorded_tree(), _groups()["OG8_0003303"]
    assert (len(proteins), sum(proteins.values())) == (736, 1068)
    assert PhyleticExpression.parse("ALL=736T AND ALL=1068").holds_for(proteins, tree)
    assert not PhyleticExpression.parse("ALL=736T AND ALL=736").holds_for(
        proteins, tree
    )
    assert not PhyleticExpression.parse("ALL>=1069").holds_for(proteins, tree)


def test_or_holds_when_one_term_holds() -> None:
    tree, proteins = _recorded_tree(), _groups()["OG8_0031041"]
    assert PhyleticExpression.parse("APIC=0T OR APIC=139").holds_for(proteins, tree)
    assert not PhyleticExpression.parse("APIC=0T OR APIC>139").holds_for(proteins, tree)


_ABSENT = "orthomcl_groups_absent_from_a_panel"
_GROUPED = "orthomcl_groups_of_a_grouped_expression"
_MORE = "orthomcl_groups_with_more_proteins_in_one_genome"
_EQUAL = "orthomcl_group_with_equal_proteins_in_two_genomes"


def test_every_group_absent_from_the_panel_fails_the_ceiling_alone() -> None:
    tree, groups, asked = _recorded_tree(), _groups(_ABSENT), _asked(_ABSENT)
    genome, panel = ("+".join(unit.codes) for unit in asked.units())
    ceiling = PhyleticExpression.parse(f"{genome}>=1T AND {panel}<=17T")
    with_none = PhyleticExpression.parse(
        f"{genome}>=1T AND {panel}=0T OR {genome}>=1T AND {panel}<=17T"
    )

    assert asked.render() == f"{genome}>=1T AND {panel}=0T"
    assert len(groups) == 7
    assert all(asked.holds_for(proteins, tree) for proteins in groups.values())
    assert not any(ceiling.holds_for(proteins, tree) for proteins in groups.values())
    assert all(with_none.holds_for(proteins, tree) for proteins in groups.values())


def test_the_groups_of_a_grouped_expression_meet_its_site_reading_only() -> None:
    tree, groups, asked = _recorded_tree(), _groups(_GROUPED), _asked(_GROUPED)

    assert sorted(groups) == [
        "OG8_0000000",
        "OG8_0000002",
        "OG8_0000004",
        "OG8_0000005",
        "OG8_0000006",
    ]
    assert all(asked.holds_for(proteins, tree) for proteins in groups.values())
    assert not any(asked.root.holds_for(proteins, tree) for proteins in groups.values())
    with pytest.raises(ValidationError):
        check_expression(asked, tree)


def test_a_two_genome_comparison_reads_the_same_with_or_without_parentheses() -> None:
    tree, asked = _recorded_tree(), _asked(_MORE)
    bare = PhyleticExpression.parse(
        " OR ".join(f"pfal={k} AND tgon>={k + 1}" for k in range(112))
    )

    assert len(asked.units()) == 224
    assert asked == bare == asked.site_reading()
    check_expression(asked, tree)


def test_a_two_genome_comparison_holds_on_the_recorded_groups() -> None:
    tree, asked = _recorded_tree(), _asked(_MORE)
    more, equal = _groups(_MORE), _groups(_EQUAL)

    assert sorted(more) == ["OG8_0000003", "OG8_0000011", "OG8_0000016"]
    assert all(asked.holds_for(proteins, tree) for proteins in more.values())
    assert "pfal" not in more["OG8_0000016"]
    assert (equal["OG8_0000001"]["pfal"], equal["OG8_0000001"]["tgon"]) == (1, 1)
    assert not asked.holds_for(equal["OG8_0000001"], tree)
    assert _asked(_EQUAL).holds_for(equal["OG8_0000001"], tree)
