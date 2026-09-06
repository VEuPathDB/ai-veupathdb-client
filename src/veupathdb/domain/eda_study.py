"""The study tree an EDA question is asked over.

The shapes are structural, so this module imports no other layer.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Protocol, runtime_checkable

VEUPATHDB_GENE_ID = "VEUPATHDB_GENE_ID"

CATEGORY_TYPE = "category"

_LISTED_LIMIT = 20


class VariableFacts(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def type(self) -> str: ...
    @property
    def display_name(self) -> str: ...
    @property
    def display_type(self) -> str: ...
    @property
    def parent_id(self) -> str | None: ...


@runtime_checkable
class ValueVariableFacts(VariableFacts, Protocol):
    """A variable that carries data. A ``category`` node carries none."""

    @property
    def vocabulary(self) -> Sequence[str] | None: ...
    @property
    def is_multi_valued(self) -> bool: ...


class EntityFacts(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def display_name(self) -> str: ...
    @property
    def variables(self) -> Sequence[VariableFacts]: ...
    @property
    def children(self) -> Sequence[EntityFacts]: ...


class StudyFacts(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def root_entity(self) -> EntityFacts: ...


def walk_entities(root: EntityFacts) -> Iterator[EntityFacts]:
    """Yield the root and then every descendant, depth first."""
    yield root
    for child in root.children:
        yield from walk_entities(child)


def entity_by_id(root: EntityFacts, entity_id: str) -> EntityFacts | None:
    for entity in walk_entities(root):
        if entity.id == entity_id:
            return entity
    return None


def variable_by_id(entity: EntityFacts, variable_id: str) -> VariableFacts | None:
    for variable in entity.variables:
        if variable.id == variable_id:
            return variable
    return None


def ancestor_entity_ids(root: EntityFacts, entity_id: str) -> frozenset[str]:
    """Every entity strictly above ``entity_id``.

    Empty both when the id names the root and when the tree does not carry it.
    """
    return _ancestors(root, entity_id, ())


def _ancestors(
    entity: EntityFacts,
    entity_id: str,
    above: tuple[str, ...],
) -> frozenset[str]:
    if entity.id == entity_id:
        return frozenset(above)
    for child in entity.children:
        found = _ancestors(child, entity_id, (*above, entity.id))
        if found:
            return found
    return frozenset()


def vocabulary_of(variable: VariableFacts) -> Sequence[str] | None:
    match variable:
        case ValueVariableFacts():
            return variable.vocabulary
        case _:
            return None


def is_multi_valued(variable: VariableFacts) -> bool:
    match variable:
        case ValueVariableFacts():
            return variable.is_multi_valued
        case _:
            return False


def listed(values: Iterable[object]) -> str:
    """Name a set of ids or values, cut to a length a message can hold."""
    items = [str(value) for value in values]
    if len(items) <= _LISTED_LIMIT:
        return ", ".join(items)
    kept = ", ".join(items[:_LISTED_LIMIT])
    return f"{kept} and {len(items) - _LISTED_LIMIT} more"
