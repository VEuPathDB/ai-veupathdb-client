"""The study-level EDA predicates: the gene entity, and a whole filter array.

The shapes are structural, so this module imports no other layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from veupathdb.domain.eda_filter_checks import (
    CHECKS,
    DeclaredRanges,
    FilterFacts,
    Site,
    strings_of,
)
from veupathdb.domain.eda_study import (
    VEUPATHDB_GENE_ID,
    StudyFacts,
    VariableFacts,
    entity_by_id,
    is_multi_valued,
    listed,
    variable_by_id,
    walk_entities,
)


@dataclass(frozen=True, slots=True)
class GeneEntityResult:
    """The entity carrying the reserved gene id, or why there is not one."""

    entity_id: str | None
    error: str | None


def find_gene_entity(study: StudyFacts, *, subject: str) -> GeneEntityResult:
    """The study must carry exactly one ``VEUPATHDB_GENE_ID`` to export genes.

    ``subject`` names what the caller exports the gene list to, so the message
    reads in the host's own vocabulary.
    """
    holders = [
        entity.id
        for entity in walk_entities(study.root_entity)
        if variable_by_id(entity, VEUPATHDB_GENE_ID) is not None
    ]
    if not holders:
        return GeneEntityResult(
            entity_id=None,
            error=(
                f"Study {study.id} carries no {VEUPATHDB_GENE_ID} variable, so it "
                f"cannot export a gene list to a {subject}."
            ),
        )
    if len(holders) > 1:
        return GeneEntityResult(
            entity_id=None,
            error=(
                f"Study {study.id} carries {VEUPATHDB_GENE_ID} on more than one "
                f"entity ({', '.join(sorted(holders))}), and the gene bridge "
                f"requires exactly one."
            ),
        )
    return GeneEntityResult(entity_id=holders[0], error=None)


def validate_filters(
    study: StudyFacts,
    filters: Sequence[FilterFacts],
    declared_ranges: DeclaredRanges | None = None,
) -> list[str]:
    """Every reason this filter array will not mean what it says.

    An empty list means the service will answer about the subset the author
    described. The service accepts several of these and answers count 0.
    """
    errors: list[str] = []
    for entry in filters:
        errors.extend(_one_filter(study, entry, declared_ranges or {}))
    errors.extend(_repeated_single_valued(study, filters))
    return errors


def _one_filter(
    study: StudyFacts,
    entry: FilterFacts,
    declared_ranges: DeclaredRanges,
) -> list[str]:
    entity = entity_by_id(study.root_entity, entry.entity_id)
    if entity is None:
        known = [known.id for known in walk_entities(study.root_entity)]
        return [
            (
                f"Filter {entry.type} names entity {entry.entity_id}, which study "
                f"{study.id} does not carry. Its entities are {listed(known)}."
            )
        ]
    variable = variable_by_id(entity, entry.variable_id)
    if variable is None:
        return [
            (
                f"Filter {entry.type} names variable {entry.variable_id}, which entity "
                f"{entity.id} does not declare. A variable id is only valid on the "
                f"entity that declares it."
            )
        ]
    if entry.type not in CHECKS:
        return [
            (
                f"Filter type {entry.type} is not one the service deserializes. The "
                f"types are {listed(sorted(CHECKS))}."
            )
        ]
    return CHECKS[entry.type](Site(entry, entity, variable, declared_ranges))


def _repeated_single_valued(
    study: StudyFacts,
    filters: Sequence[FilterFacts],
) -> list[str]:
    sets: dict[tuple[str, str], list[frozenset[str]]] = {}
    for entry in filters:
        variable = _single_valued_target(study, entry)
        if variable is None:
            continue
        members = frozenset(strings_of(entry))
        if members:
            sets.setdefault((entry.entity_id, variable.id), []).append(members)
    errors: list[str] = []
    for (entity_id, variable_id), grouped in sets.items():
        if len(grouped) == 1 or frozenset.intersection(*grouped):
            continue
        written = "; ".join(f"({listed(sorted(one))})" for one in grouped)
        errors.append(
            f"Filters on variable {variable_id} of entity {entity_id} name the "
            f"disjoint sets {written}, and the variable holds one value per row, "
            f"so the subset is empty. Express OR with one filter that holds "
            f"several members, never with two array entries."
        )
    return errors


def _single_valued_target(
    study: StudyFacts,
    entry: FilterFacts,
) -> VariableFacts | None:
    if entry.type != "stringSet":
        return None
    entity = entity_by_id(study.root_entity, entry.entity_id)
    if entity is None:
        return None
    variable = variable_by_id(entity, entry.variable_id)
    if variable is None or is_multi_valued(variable):
        return None
    return variable
