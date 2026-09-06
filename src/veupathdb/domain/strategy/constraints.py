from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Literal

from pydantic import Field

from veupathdb.model import CamelModel


class ConstraintKind(StrEnum):
    DATA_TYPE = "data_type"
    STATISTICAL_THRESHOLD = "statistical_threshold"
    FOLD_CHANGE = "fold_change"
    COMPARATOR = "comparator"
    ORGANISM = "organism"
    RECORD_TYPE = "record_type"
    PERCENTILE = "percentile"
    COMBINATION = "combination"
    OTHER = "other"


class ConstraintSource(StrEnum):
    USER_EXPLICIT = "user_explicit"
    ASSUMED = "assumed"


class ConstraintStatus(StrEnum):
    PROVISIONAL = "provisional"
    GROUNDED = "grounded"
    SUBSTITUTED = "substituted"
    UNGROUNDABLE = "ungroundable"


class Constraint(CamelModel):
    kind: ConstraintKind
    requested_value: str = Field(min_length=1)
    label: str = Field(min_length=1)
    source: ConstraintSource = ConstraintSource.ASSUMED
    hard: bool = True
    """A hard requirement ('RNA-Seq only') blocks if unmet; a soft preference
    ('RNA-Seq preferred, microarray fallback ok') is surfaced but never blocks."""


class GroundedConstraint(CamelModel):
    constraint: Constraint
    status: ConstraintStatus
    realized_value: str | None = None
    note: str = ""


_UNMET = {ConstraintStatus.UNGROUNDABLE, ConstraintStatus.SUBSTITUTED}


def is_blocking(grounded: GroundedConstraint) -> bool:
    return (
        grounded.constraint.source is ConstraintSource.USER_EXPLICIT
        and grounded.constraint.hard
        and grounded.status in _UNMET
    )


def provisional_constraints(constraints: list[Constraint]) -> list[GroundedConstraint]:
    """Wrap constraints as ``provisional`` — captured but not yet grounded (no
    plan exists to compare against). Provisional constraints never block; they
    surface in the ledger so the user sees what was captured pre-plan."""

    return [
        GroundedConstraint(constraint=c, status=ConstraintStatus.PROVISIONAL)
        for c in constraints
    ]


def organism_hints_from(requirements: Sequence[Constraint]) -> list[str]:
    """The organisms the requirements state, in the order stated, without repeats."""
    return list(
        dict.fromkeys(
            c.requested_value for c in requirements if c.kind is ConstraintKind.ORGANISM
        )
    )


def combination_requirements_from(
    requirements: Sequence[Constraint],
) -> list[Constraint]:
    """The stated combinations, in the order stated."""
    return [c for c in requirements if c.kind is ConstraintKind.COMBINATION]


_Dimension = tuple[ConstraintKind, str]


def _dimension(c: Constraint) -> _Dimension:
    """What a constraint collapses on.

    A combination names the criteria it is about, so two of them are two
    dimensions; every other kind holds one value per kind.
    """
    if c.kind is ConstraintKind.COMBINATION:
        return (c.kind, c.requested_value)
    return (c.kind, "")


def merge_constraints(
    provisional: list[Constraint], explicit: list[Constraint]
) -> list[Constraint]:
    """Merge scoping's provisional (assumed) constraints with constraints the
    user stated in their latest message. The explicit set wins per dimension
    and is forced to ``user_explicit`` — anything the user literally
    states is explicit by construction, regardless of how the LLM tagged it."""

    by_dimension: dict[_Dimension, Constraint] = {_dimension(c): c for c in provisional}
    for c in explicit:
        by_dimension[_dimension(c)] = c.model_copy(
            update={"source": ConstraintSource.USER_EXPLICIT}
        )
    return list(by_dimension.values())


_SHARE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)", re.IGNORECASE)
_TOP_RE = re.compile(r"\btop\b|\bhighest\b", re.IGNORECASE)
_BOTTOM_RE = re.compile(r"\bbottom\b|\blowest\b", re.IGNORECASE)
_FULL_SCALE = 100.0


class PercentileRequest(CamelModel):
    """A share of a ranked population, read from what the user stated."""

    direction: Literal["top", "bottom"]
    share: float

    @classmethod
    def parse(cls, text: str) -> PercentileRequest | None:
        share = _SHARE_RE.search(text)
        if share is None:
            return None
        if _TOP_RE.search(text):
            direction: Literal["top", "bottom"] = "top"
        elif _BOTTOM_RE.search(text):
            direction = "bottom"
        else:
            return None
        return cls(direction=direction, share=float(share.group(1)))

    @property
    def bound(self) -> float:
        """The percentile value that realizes this share."""
        return _FULL_SCALE - self.share if self.direction == "top" else self.share

    def share_of(self, bound: float) -> float:
        return _FULL_SCALE - bound if self.direction == "top" else bound


CombinationOperator = Literal["OR", "AND"]

_SEPARATORS: dict[CombinationOperator, str] = {"OR": " OR ", "AND": " AND "}
_MIN_COMBINATION_TERMS = 2


class CombinationRequest(CamelModel):
    """How the user said their evidence lines combine: one operator over the
    phrases that name the criteria.

    The phrases are the anchor, not criterion ids: a build renumbers the
    criteria on the step ids it mints, and the words survive that.
    """

    operator: CombinationOperator
    terms: list[str] = Field(min_length=_MIN_COMBINATION_TERMS)

    @classmethod
    def parse(cls, text: str) -> CombinationRequest | None:
        """Read one operator over two or more terms, or nothing.

        The operator is an uppercase word between spaces. A string that holds
        both operators states no single combination, so it is unparseable.
        """
        stated: list[CombinationOperator] = [
            operator for operator, separator in _SEPARATORS.items() if separator in text
        ]
        if len(stated) != 1:
            return None
        operator = stated[0]
        terms = [part.strip() for part in text.split(_SEPARATORS[operator])]
        if len(terms) < _MIN_COMBINATION_TERMS or not all(terms):
            return None
        return cls(operator=operator, terms=terms)

    @property
    def expression(self) -> str:
        """The combination as one line, in the user's own words."""
        return _SEPARATORS[self.operator].join(self.terms)
