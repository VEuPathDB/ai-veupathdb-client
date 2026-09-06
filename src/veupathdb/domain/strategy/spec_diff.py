"""What one turn did to the spec it started from.

A criterion is kept, changed, added or dropped. The comparison is computed from
the two specs, so no prose can claim a criterion was preserved that was not.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, computed_field

from veupathdb.domain.parameters.value_codec import to_wire
from veupathdb.domain.strategy.operational_spec import Criterion, OperationalSpec
from veupathdb.model import CamelModel

__all__ = ["CriterionChange", "CriterionDisposition", "SpecDiff", "diff_specs"]

CriterionDisposition = Literal["kept", "changed", "added", "dropped"]


class CriterionChange(CamelModel):
    """One criterion's fate across a turn.

    ``changed_params`` names every parameter whose value the turn moved, in
    wire form. It is a report; the values to push come from the spec itself.
    """

    criterion_id: str
    disposition: CriterionDisposition
    changed_params: dict[str, str] = Field(default_factory=dict)
    reason: str = ""


class SpecDiff(CamelModel):
    changes: list[CriterionChange] = Field(default_factory=list)
    structure_changed: bool = False

    @computed_field
    def kept_count(self) -> int:
        return self._count("kept")

    @computed_field
    def changed_count(self) -> int:
        return self._count("changed")

    @computed_field
    def added_count(self) -> int:
        return self._count("added")

    @computed_field
    def dropped_count(self) -> int:
        return self._count("dropped")

    def _count(self, disposition: CriterionDisposition) -> int:
        return sum(1 for c in self.changes if c.disposition == disposition)

    def touched_count(self) -> int:
        """Criteria this turn added, changed or dropped, and the shape it rewired.

        A rewire moves the result set without touching a criterion, so it counts
        as one touch.
        """
        touched = sum(1 for c in self.changes if c.disposition != "kept")
        return touched + (1 if self.structure_changed else 0)

    def render(self) -> str:
        counts = (
            f"kept {self.kept_count}, changed {self.changed_count}, "
            f"added {self.added_count}, dropped {self.dropped_count}"
        )
        return f"{counts}, structure rewired" if self.structure_changed else counts


def diff_specs(before: OperationalSpec, after: OperationalSpec) -> SpecDiff:
    """Compare two specs by criterion id and by bound parameter value."""
    after_by_id = {c.id: c for c in after.criteria}
    changes = [
        _change_for(criterion, after_by_id.get(criterion.id))
        for criterion in before.criteria
    ]
    before_ids = {c.id for c in before.criteria}
    changes.extend(
        CriterionChange(
            criterion_id=criterion.id,
            disposition="added",
            changed_params=_wire(criterion),
        )
        for criterion in after.criteria
        if criterion.id not in before_ids
    )
    return SpecDiff(
        changes=changes,
        structure_changed=before.structure != after.structure,
    )


def _change_for(before: Criterion, after: Criterion | None) -> CriterionChange:
    if after is None:
        return CriterionChange(
            criterion_id=before.id,
            disposition="dropped",
            reason=before.text,
        )
    before_params = _wire(before)
    after_params = _wire(after)
    if before_params == after_params and before.search_name == after.search_name:
        return CriterionChange(criterion_id=before.id, disposition="kept")
    return CriterionChange(
        criterion_id=before.id,
        disposition="changed",
        changed_params={
            name: value
            for name, value in after_params.items()
            if before_params.get(name) != value
        },
    )


def _wire(criterion: Criterion) -> dict[str, str]:
    return {name: to_wire(value) for name, value in criterion.resolved_params.items()}
