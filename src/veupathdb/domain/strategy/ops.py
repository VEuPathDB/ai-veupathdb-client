"""Combine operators and colocation parameters for strategy building."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from veupathdb.model import CamelModel


class CombineOp(StrEnum):
    """Set operations that combine two step results.

    WDK defines the same set. LONLY matches MINUS and RONLY matches RMINUS.
    Both names stay, for round-trip fidelity with WDK.
    """

    INTERSECT = "INTERSECT"
    MINUS = "MINUS"
    RMINUS = "RMINUS"
    LONLY = "LONLY"
    RONLY = "RONLY"
    COLOCATE = "COLOCATE"
    UNION = "UNION"


DEFAULT_COMBINE_OPERATOR = CombineOp.INTERSECT

BOOLEAN_OPERATORS = frozenset(CombineOp) - {CombineOp.COLOCATE}
"""The operators that the WDK boolean search accepts."""


def _must_be_boolean(op: CombineOp) -> CombineOp:
    if op not in BOOLEAN_OPERATORS:
        msg = (
            f"{op.value} is not a boolean operator; "
            "WDK does colocation through GenesBySpanLogic"
        )
        raise ValueError(msg)
    return op


BooleanOperator = Annotated[CombineOp, AfterValidator(_must_be_boolean)]
"""A combine operator that the WDK boolean search accepts.

COLOCATE is a combine operator but not a boolean one. Every field of a boolean
search config uses this type.
"""

BOOLEAN_OPERATOR_OPTIONS_DESC = ", ".join(
    o.value for o in (CombineOp.INTERSECT, CombineOp.UNION, CombineOp.MINUS)
)


class ColocationParams(CamelModel):
    """Span-logic parameters for the COLOCATE operator.

    Field values are readable words. Serialization translates them to the WDK
    vocabulary values.
    """

    operation: Literal["overlaps", "contains", "is contained in"] = "overlaps"
    strand: Literal["either strand", "same strand", "opposite strand"] = "either strand"
    output: Literal["a", "b"] = "a"

    # Region A is the gene result set.
    region_a: Literal["exact", "upstream", "downstream", "custom"] = "custom"
    begin_a: Literal["start", "stop"] = "start"
    begin_direction_a: Literal["+", "-"] = "-"
    begin_offset_a: int = Field(default=1000, ge=0)
    end_a: Literal["start", "stop"] = "stop"
    end_direction_a: Literal["+", "-"] = "+"
    end_offset_a: int = Field(default=0, ge=0)

    # Region B is the feature set.
    region_b: Literal["exact", "upstream", "downstream", "custom"] = "exact"
    begin_b: Literal["start", "stop"] = "start"
    begin_direction_b: Literal["+", "-"] = "+"
    begin_offset_b: int = Field(default=0, ge=0)
    end_b: Literal["start", "stop"] = "stop"
    end_direction_b: Literal["+", "-"] = "+"
    end_offset_b: int = Field(default=0, ge=0)

    def to_wdk_params(self) -> dict[str, str]:
        """Serialize to the WDK span-logic parameters, with vocabulary values."""
        return {
            "span_sentence": "colocation",
            "span_operation": _OPERATION_TO_WDK[self.operation],
            "span_strand": _STRAND_TO_WDK[self.strand],
            "span_output": self.output,
            "region_a": self.region_a,
            "span_begin_a": self.begin_a,
            "span_begin_direction_a": self.begin_direction_a,
            "span_begin_offset_a": str(self.begin_offset_a),
            "span_end_a": self.end_a,
            "span_end_direction_a": self.end_direction_a,
            "span_end_offset_a": str(self.end_offset_a),
            "region_b": self.region_b,
            "span_begin_b": self.begin_b,
            "span_begin_direction_b": self.begin_direction_b,
            "span_begin_offset_b": str(self.begin_offset_b),
            "span_end_b": self.end_b,
            "span_end_direction_b": self.end_direction_b,
            "span_end_offset_b": str(self.end_offset_b),
        }


# The REST API takes the internal vocabulary value, not the display value.
_OPERATION_TO_WDK: dict[str, str] = {
    "overlaps": "overlap",
    "contains": "a_contain_b",
    "is contained in": "b_contain_a",
}

_STRAND_TO_WDK: dict[str, str] = {
    "either strand": "Both strands",
    "same strand": "same strand",
    "opposite strand": "opposite strand",
}


_OP_ALIASES: dict[str, CombineOp] = {
    "AND": CombineOp.INTERSECT,
    "INTERSECTION": CombineOp.INTERSECT,
    "OR": CombineOp.UNION,
    "PLUS": CombineOp.UNION,
    "UNION": CombineOp.UNION,
    "INTERSECT": CombineOp.INTERSECT,
    "MINUS": CombineOp.MINUS,
    "NOT": CombineOp.MINUS,
    "RMINUS": CombineOp.RMINUS,
    "LONLY": CombineOp.LONLY,
    "RONLY": CombineOp.RONLY,
    "LEFT_MINUS": CombineOp.MINUS,
    "RIGHT_MINUS": CombineOp.RMINUS,
    "LMINUS": CombineOp.MINUS,
    "MINUS_LEFT": CombineOp.MINUS,
    "MINUS_RIGHT": CombineOp.RMINUS,
    "COLOCATE": CombineOp.COLOCATE,
}


def parse_op(value: str) -> CombineOp:
    """Parse a combine operator from a name or an alias.

    :raises ValueError: If the value is empty or unknown.
    """
    raw = (value or "").strip()
    if not raw:
        msg = "Unknown operator: <empty>"
        raise ValueError(msg)

    norm = raw.upper().replace("-", "_").replace(" ", "_")
    if norm in _OP_ALIASES:
        return _OP_ALIASES[norm]

    try:
        return CombineOp(norm)
    except ValueError as exc:
        msg = f"Unknown operator: {value}"
        raise ValueError(msg) from exc
