"""Combine operators and colocation parameters for strategy building."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from veupathdb.errors import DataParsingError
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
        words = self.model_dump()
        words["operation"] = _OPERATION_TO_WDK[self.operation]
        words["strand"] = _STRAND_TO_WDK[self.strand]
        return {"span_sentence": "colocation"} | {
            wdk: str(words[field]) for field, wdk in _FIELD_TO_WDK.items()
        }

    @classmethod
    def from_wdk_params(cls, params: Mapping[str, str]) -> ColocationParams:
        missing = [wdk for wdk in _FIELD_TO_WDK.values() if wdk not in params]
        if missing:
            msg = f"span logic step has no {', '.join(missing)}"
            raise DataParsingError(msg)
        words = {field: params[wdk] for field, wdk in _FIELD_TO_WDK.items()}
        words["operation"] = _word_for(
            _OPERATION_FROM_WDK, "span_operation", words["operation"]
        )
        words["strand"] = _word_for(_STRAND_FROM_WDK, "span_strand", words["strand"])
        return cls.model_validate(words)


def _word_for(vocabulary: Mapping[str, str], key: str, value: str) -> str:
    if value not in vocabulary:
        msg = f"{key} {value!r} is not one of {', '.join(vocabulary)}"
        raise DataParsingError(msg)
    return vocabulary[value]


_FIELD_TO_WDK: dict[str, str] = {
    "operation": "span_operation",
    "strand": "span_strand",
    "output": "span_output",
    "region_a": "region_a",
    "begin_a": "span_begin_a",
    "begin_direction_a": "span_begin_direction_a",
    "begin_offset_a": "span_begin_offset_a",
    "end_a": "span_end_a",
    "end_direction_a": "span_end_direction_a",
    "end_offset_a": "span_end_offset_a",
    "region_b": "region_b",
    "begin_b": "span_begin_b",
    "begin_direction_b": "span_begin_direction_b",
    "begin_offset_b": "span_begin_offset_b",
    "end_b": "span_end_b",
    "end_direction_b": "span_end_direction_b",
    "end_offset_b": "span_end_offset_b",
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


_OPERATION_FROM_WDK = {wdk: word for word, wdk in _OPERATION_TO_WDK.items()}
_STRAND_FROM_WDK = {wdk: word for word, wdk in _STRAND_TO_WDK.items()}


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
