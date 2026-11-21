"""The clauses of a WDK filter value and the facets that bind a stated clause."""

from __future__ import annotations

import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated, Any, Literal, Protocol, Self

from pydantic import (
    ConfigDict,
    Discriminator,
    Field,
    JsonValue,
    RootModel,
    Tag,
    TypeAdapter,
    model_validator,
)
from pydantic import ValidationError as PydanticValidationError
from pydantic.alias_generators import to_camel

from veupathdb.domain.parameters.date_bounds import ISODate
from veupathdb.domain.parameters.wdk_vocab import WDKFilterOntologyTerm
from veupathdb.errors import ValidationError
from veupathdb.model import CamelModel

ClauseKey = tuple[str, bool, bool, frozenset[str]]


class _Bounds(CamelModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def _one_bound(self) -> Self:
        if not self.model_dump(exclude_none=True):
            msg = "a range states min, max or both"
            raise ValueError(msg)
        return self


class NumberBounds(_Bounds):
    min: float | None = None
    max: float | None = None


class DateBounds(_Bounds):
    min: ISODate | None = None
    max: ISODate | None = None


class _Clause(CamelModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, frozen=True, extra="ignore"
    )
    field: str
    type: str
    is_range: bool
    include_unknown: bool

    def _terms(self) -> frozenset[str]:
        raise NotImplementedError

    @property
    def key(self) -> ClauseKey:
        return (self.field, self.is_range, self.include_unknown, self._terms())


class StringMembers(_Clause):
    type: Literal["string"]
    is_range: Literal[False]
    value: list[str | None]

    def _terms(self) -> frozenset[str]:
        return frozenset(str(member) for member in self.value)


class NumberMembers(_Clause):
    type: Literal["number"]
    is_range: Literal[False]
    value: list[float | None]

    def _terms(self) -> frozenset[str]:
        return frozenset(str(member) for member in self.value)


class NumberRange(_Clause):
    type: Literal["number"]
    is_range: Literal[True]
    value: NumberBounds

    def _terms(self) -> frozenset[str]:
        return frozenset(f"{k}={v}" for k, v in self.value.model_dump().items())


class DateRange(_Clause):
    type: Literal["date"]
    is_range: Literal[True]
    value: DateBounds

    def _terms(self) -> frozenset[str]:
        return frozenset(f"{k}={v}" for k, v in self.value.model_dump().items())


class MultiFilterValue(CamelModel):
    model_config = ConfigDict(frozen=True)
    operation: Literal["union", "intersect"]
    filters: list[StringMembers]


class MultiMembers(_Clause):
    type: Literal["multiFilter"]
    is_range: Literal[False]
    value: MultiFilterValue

    def _terms(self) -> frozenset[str]:
        leaves = (str(sorted(leaf.key[3])) for leaf in self.value.filters)
        return frozenset((self.value.operation, *leaves))


def _clause_tag(raw: Any) -> str:
    if isinstance(raw, _Clause):
        return f"{raw.type}:{raw.is_range}"
    if isinstance(raw, dict):
        return f"{raw.get('type')}:{raw.get('isRange')}"
    return ""


FilterClause = Annotated[
    Annotated[StringMembers, Tag("string:False")]
    | Annotated[NumberMembers, Tag("number:False")]
    | Annotated[NumberRange, Tag("number:True")]
    | Annotated[DateRange, Tag("date:True")]
    | Annotated[MultiMembers, Tag("multiFilter:False")],
    Discriminator(_clause_tag),
]

_CLAUSE: TypeAdapter[FilterClause] = TypeAdapter(FilterClause)


class FilterValue(CamelModel):
    type: Literal["filter"] = "filter"
    filters: list[FilterClause] = Field(default_factory=list)

    def to_wire(self) -> str:
        return json.dumps(self.to_decoded())

    def to_decoded(self) -> JsonValue:
        dumped = self.model_dump(by_alias=True, mode="json", exclude_none=True)
        return {"filters": dumped["filters"]}

    @property
    def clause_set(self) -> frozenset[ClauseKey]:
        """The clauses this value states. Their order is not part of it."""
        return frozenset(clause.key for clause in self.filters)


class FilterProposal(CamelModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    value: list[str | float] | dict[str, float | str | None]
    include_unknown: bool = False


class FilterProposals(RootModel[Annotated[list[FilterProposal], Field(min_length=1)]]):
    pass


class FilterStatementError(ValidationError):
    def __init__(self, faults: list[str]) -> None:
        self.faults = faults
        super().__init__(
            title="Invalid filter statement",
            detail="\n".join(faults),
            errors=[{"detail": fault} for fault in faults],
        )


class _ValueCount(Protocol):
    @property
    def value(self) -> str | int | float | None: ...
    @property
    def count(self) -> int: ...


class _TermSummary(Protocol):
    @property
    def value_counts(self) -> Sequence[_ValueCount]: ...
    @property
    def internals_count(self) -> int: ...


class _FilterDeclaration(Protocol):
    @property
    def ontology(self) -> Sequence[WDKFilterOntologyTerm]: ...
    @property
    def values(self) -> dict[str, list[str]] | None: ...


def _shown(bound: float | str) -> str:
    return bound if isinstance(bound, str) else f"{Decimal(repr(bound)).normalize():,f}"


class FacetRange(CamelModel):
    min: float | str
    max: float | str
    records: int
    units: str | None

    @classmethod
    def of(cls, summary: _TermSummary, facet: FilterFacet) -> FacetRange | None:
        order = str if facet.type == "date" else float
        counted = sorted(
            (
                v.value
                for v in summary.value_counts
                if v.count > 0 and v.value is not None
            ),
            key=order,
        )
        if not counted:
            return None
        return cls(
            min=counted[0],
            max=counted[-1],
            records=summary.internals_count,
            units=facet.units,
        )

    def selects(self, bounds: NumberBounds | DateBounds) -> bool:
        low = self.min if bounds.min is None else bounds.min
        high = self.max if bounds.max is None else bounds.max
        return (
            min(low, self.max) == low
            and max(high, self.min) == high
            and min(low, high) == low
        )

    def text(self) -> str:
        units = f" {self.units}" if self.units else ""
        return f"{_shown(self.min)} to {_shown(self.max)}{units} over {self.records:,} records"


class FilterFacet(CamelModel):
    term: str
    display: str
    parent: str | None
    type: Literal["string", "number", "date", "multiFilter"]
    is_range: bool
    units: str | None
    precision: int
    members: list[str]
    range: FacetRange | None = None

    @property
    def ranged(self) -> bool:
        return self.is_range or self.type == "date"

    def form(self) -> str:
        bound = '"<yyyy-mm-dd>"' if self.type == "date" else "<n>"
        value = (
            f'{{"min": {bound}, "max": {bound}}}'
            if self.ranged
            else '["<member>", ...]'
        )
        tail = " with either bound left out" if self.ranged else ""
        return f'{self.term} ({self.display}) takes {{"field": "{self.term}", "value": {value}}}{tail}'

    def clause(self, proposal: FilterProposal) -> FilterClause:
        try:
            clause = _CLAUSE.validate_python(
                {
                    "field": self.term,
                    "type": self.type,
                    "isRange": self.ranged,
                    "includeUnknown": proposal.include_unknown,
                    "value": proposal.value,
                }
            )
        except PydanticValidationError:
            read = json.dumps(proposal.value)
            raise FilterStatementError([f"{self.form()}; it read {read}."]) from None
        unknown = sorted({str(v) for v in proposal.value} - set(self.members))
        if self.members and not self.ranged and unknown:
            text = (
                f"{self.term} ({self.display}) has no member {', '.join(unknown)}; "
                f"its members are {', '.join(self.members)}."
            )
            raise FilterStatementError([text])
        return clause


class FilterFacets(RootModel[list[FilterFacet]]):
    @classmethod
    def of(cls, param: _FilterDeclaration) -> FilterFacets:
        values = param.values or {}
        return cls(
            [
                FilterFacet(
                    term=term.term,
                    display=term.display or term.term,
                    parent=term.parent,
                    type=term.type,
                    is_range=term.is_range,
                    units=term.units,
                    precision=term.precision,
                    members=values.get(term.term, []),
                )
                for term in param.ontology
                if term.type is not None
            ]
        )

    def find(self, name: str) -> FilterFacet | None:
        return next((f for f in self.root if name in (f.term, f.display)), None)

    def bind(self, proposals: FilterProposals) -> FilterValue:
        return self._bound(proposals.root)

    def held(self, value: FilterValue) -> FilterValue:
        return self._bound(
            [
                FilterProposal.model_validate(
                    clause.model_dump(
                        by_alias=True,
                        mode="json",
                        exclude_none=True,
                        include={"field", "value", "include_unknown"},
                    )
                )
                for clause in value.filters
            ]
        )

    def _bound(self, proposals: Sequence[FilterProposal]) -> FilterValue:
        clauses: list[FilterClause] = []
        faults: list[str] = []
        for proposal in proposals:
            facet = self.find(proposal.field)
            if facet is None:
                terms = ", ".join(f.term for f in self.root)
                faults.append(
                    f"No facet is named {proposal.field!r}; the facets are {terms}."
                )
                continue
            try:
                clauses.append(facet.clause(proposal))
            except FilterStatementError as refusal:
                faults.extend(refusal.faults)
        if faults:
            raise FilterStatementError(faults)
        return FilterValue(filters=clauses)
