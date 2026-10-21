"""Reads the phyletic clade tree off a WDK search definition, or off OrthoMCL's
taxon tables."""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from veupathdb import JSONObject
from veupathdb.domain.parameters.phyletic import (
    PHYLETIC_PARAM_NAMES,
    PhyleticTree,
    TaxonEntry,
)
from veupathdb.wdk.wdk_models import WDKAnswer
from veupathdb.wdk.wdk_parameters import WDKParameter

ORTHO_TAXONOMY_RECORD_TYPE = "helper"
ORTHO_TAXONOMY_SEARCH = "ByDefault"
ORTHO_TAXONOMY_REPORT: JSONObject = {
    "attributes": ["primary_key"],
    "tables": ["RootTaxons", "Taxons"],
}
"""OrthoMCL's taxonomy: one helper record whose two tables hold the clades and
the species, each row naming its parent by clade id."""


def phyletic_tree_of(params: list[WDKParameter]) -> PhyleticTree | None:
    """The clade tree of a phyletic search, or ``None`` when it is not one.

    A search is phyletic only when it carries all five parameter names and both
    maps are standard enum vocabularies. The indent map carries the depths, so a
    term map without it reads as a tree of roots, in which a clade holds no
    species and expands to nothing.
    """
    by_name = {p.name: p for p in params}
    if not by_name.keys() >= PHYLETIC_PARAM_NAMES:
        return None
    term_map = by_name["phyletic_term_map"].vocabulary
    indent_map = by_name["phyletic_indent_map"].vocabulary
    if not isinstance(term_map, list) or not isinstance(indent_map, list):
        return None
    if term_map and not indent_map:
        return None
    return PhyleticTree.from_vocab(term_map, indent_map)


class _TaxonRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(alias="orthomcl_clade_id")
    parent_id: str | None = None
    name: str

    @field_validator("name")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        return value.strip()


class _CladeRow(_TaxonRow):
    code: str = Field(alias="taxon_abbrev")


class _SpeciesRow(_TaxonRow):
    code: str = Field(alias="three_letter_abbrev")


class _TaxonTables(BaseModel):
    model_config = ConfigDict(extra="ignore")

    RootTaxons: list[_CladeRow]
    Taxons: list[_SpeciesRow]


def ortho_taxonomy_of(answer: WDKAnswer) -> PhyleticTree | None:
    """The tree OrthoMCL's taxon tables hold, or ``None`` when the answer lacks
    them. A ``RootTaxons`` row is a clade and a ``Taxons`` row a genome. A genome row
    repeats once per clade above it, so each code is kept once."""
    if not answer.records:
        return None
    try:
        tables = _TaxonTables.model_validate(answer.records[0].tables)
    except ValidationError:
        return None
    entries: dict[str, TaxonEntry] = {}
    listed: tuple[tuple[Sequence[_CladeRow | _SpeciesRow], bool], ...] = (
        (tables.RootTaxons, True),
        (tables.Taxons, False),
    )
    for rows, clade in listed:
        for row in rows:
            entries.setdefault(
                row.code,
                TaxonEntry(
                    id=row.id,
                    parent_id=row.parent_id,
                    code=row.code,
                    label=row.name,
                    clade=clade,
                ),
            )
    return PhyleticTree.from_taxa(list(entries.values()))
