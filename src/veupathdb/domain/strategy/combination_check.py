"""Whether a strategy tree combines criteria the way the user stated.

A stated combination names its criteria by their words. This module matches
those words to criteria and reads the operator of the node where they meet.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import NamedTuple

from veupathdb.domain.strategy.constraints import (
    CombinationOperator,
    CombinationRequest,
    Constraint,
    combination_requirements_from,
)
from veupathdb.domain.strategy.operational_spec import (
    Criterion,
    SpecStructure,
    StructureNode,
)
from veupathdb.domain.strategy.ops import CombineOp

_WORD_RE = re.compile(r"[a-z0-9]+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# Words that name no evidence. Every WDK gene search carries "genes", so a term
# that overlaps a criterion only there names nothing.
_FILLER_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "by",
        "for",
        "from",
        "gene",
        "genes",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)

_REQUIRED_OPERATOR: dict[CombinationOperator, CombineOp] = {
    "OR": CombineOp.UNION,
    "AND": CombineOp.INTERSECT,
}
_MIN_MEETING_CRITERIA = 2


def required_operator(operator: CombinationOperator) -> CombineOp:
    """The WDK combine operator a stated operator requires."""
    return _REQUIRED_OPERATOR[operator]


def _words(text: str) -> frozenset[str]:
    """The content words of a phrase, with camel-case names split apart."""
    spaced = _CAMEL_BOUNDARY_RE.sub(" ", text)
    return frozenset(_WORD_RE.findall(spaced.lower())) - _FILLER_WORDS


def combination_terms_overlap(first: str, second: str) -> bool:
    """Whether two combination statements talk about the same criteria.

    Two statements overlap when any term of one shares a content word with
    any term of the other. A statement that does not parse overlaps nothing.
    """
    a = CombinationRequest.parse(first)
    b = CombinationRequest.parse(second)
    if a is None or b is None:
        return False
    return any(
        _words(term_a) & _words(term_b) for term_a in a.terms for term_b in b.terms
    )


def _best_match(
    wanted: frozenset[str], words_by_id: Mapping[str, frozenset[str]]
) -> str | None:
    """The criterion sharing the most words with a term.

    A tie names two criteria equally well, so it matches neither.
    """
    ranked = sorted(
        ((len(wanted & words), cid) for cid, words in words_by_id.items()),
        reverse=True,
    )
    overlapping = [entry for entry in ranked if entry[0]]
    if not overlapping:
        return None
    if len(overlapping) > 1 and overlapping[0][0] == overlapping[1][0]:
        return None
    return overlapping[0][1]


def match_terms(
    terms: Sequence[str], criteria: Sequence[Criterion]
) -> dict[str, str] | None:
    """The criterion each term names, or None when the check must abstain.

    A term matches the criterion whose text and search name share the most
    words with it. The terms must name distinct criteria.
    """
    words_by_id = {c.id: _words(f"{c.text} {c.search_name}") for c in criteria}
    matched: dict[str, str] = {}
    for term in terms:
        wanted = _words(term)
        if not wanted:
            return None
        found = _best_match(wanted, words_by_id)
        if found is None:
            return None
        matched[term] = found
    if len(matched) != len(terms):
        return None
    if len(set(matched.values())) != len(matched):
        return None
    return matched


def _meeting_node(
    node: StructureNode, wanted: frozenset[str]
) -> tuple[frozenset[str], StructureNode | None]:
    """The distinct wanted criteria under this node, and where they meet.

    Distinct ids, not occurrences: a duplicated leaf must not stand in for a
    criterion that sits elsewhere in the tree.
    """
    seen = (
        frozenset({node.criterion_id}) if node.criterion_id in wanted else frozenset()
    )
    settled: StructureNode | None = None
    for child in node.inputs:
        found_ids, found = _meeting_node(child, wanted)
        seen = seen | found_ids
        if found is not None and settled is None:
            settled = found
    if settled is not None:
        return seen, settled
    if seen == wanted:
        return seen, node
    return seen, None


def meeting_operator(
    structure: SpecStructure, criterion_ids: Collection[str]
) -> CombineOp | None:
    """The operator of the node where these criteria meet.

    None when one of them is absent from the tree, or when they meet at a node
    that combines nothing. A transform is transparent: the criteria under it
    still meet at the combine above.
    """
    wanted = frozenset(criterion_ids)
    if len(wanted) < _MIN_MEETING_CRITERIA:
        return None
    _, node = _meeting_node(structure.root, wanted)
    if node is None or node.kind != "combine":
        return None
    return node.operator


def combination_violation(
    request: CombinationRequest,
    matched_ids: Collection[str],
    structure: SpecStructure,
) -> str | None:
    """Why this tree does not state the requested combination, or None."""
    required = required_operator(request.operator)
    found = meeting_operator(structure, matched_ids)
    if found is required:
        return None
    joined = "no combine node" if found is None else found.value
    return (
        f"the user requires {request.expression!r}: those criteria must meet "
        f"at {required.value}, but the tree joins them at {joined}"
    )


class CombinationBreach(NamedTuple):
    """A stated combination the tree does not honor."""

    required: CombineOp
    message: str


def first_combination_violation(
    requirements: Iterable[Constraint],
    criteria: Sequence[Criterion],
    structure: SpecStructure,
) -> CombinationBreach | None:
    """The first stated combination this tree contradicts, or None.

    The check abstains on a requirement it cannot read: one that states no
    single operator, or whose terms name no distinct criteria of this spec.
    """
    for requirement in combination_requirements_from(list(requirements)):
        request = CombinationRequest.parse(requirement.requested_value)
        if request is None:
            continue
        matched = match_terms(request.terms, criteria)
        if matched is None:
            continue
        message = combination_violation(request, matched.values(), structure)
        if message is not None:
            return CombinationBreach(
                required=required_operator(request.operator),
                message=message,
            )
    return None
