"""Step data keyed by id, with structure held as id references.

The nested tree form is rebuilt only when projecting to WDK. Step kind is stated on
the step rather than inferred from which input slots are set.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from veupathdb.domain.parameters.values import ParamValue
from veupathdb.domain.strategy.ast import (
    COMBINE_SEARCH_NAME,
    StepAnalysis,
    StepFilter,
    StepReport,
    StrategyStepNode,
)
from veupathdb.domain.strategy.ops import ColocationParams, CombineOp
from veupathdb.model import CamelModel


class StepKind(StrEnum):
    SEARCH = "search"
    TRANSFORM = "transform"
    COMBINE = "combine"


class StrategyStep(CamelModel):
    """One step, with its own data and the ids of the steps that feed it.

    A combine has no search_name, because a set operation is not a WDK question.
    """

    id: str
    kind: StepKind
    search_name: str | None = None
    record_class: str | None = None
    """The record type WDK lists this step's own search under. A transform
    crosses record classes, so it is not the class of the step it consumes."""
    parameters: dict[str, ParamValue] = Field(default_factory=dict)
    primary_input_id: str | None = None
    secondary_input_id: str | None = None
    display_name: str | None = None
    operator: CombineOp | None = None
    colocation_params: ColocationParams | None = None
    filters: list[StepFilter] = Field(default_factory=list)
    analyses: list[StepAnalysis] = Field(default_factory=list)
    reports: list[StepReport] = Field(default_factory=list)
    wdk_weight: int | None = None
    expanded_strategy_id: int | None = None
    expanded_name: str | None = None

    @property
    def display_label(self) -> str:
        """Returns the user-facing label. An unnamed combine falls back to a constant."""
        if self.display_name:
            return self.display_name
        if self.kind is StepKind.COMBINE:
            return "Combine"
        return self.search_name or self.id

    def input_ids(self) -> list[str]:
        """Returns the input step ids in slot order and omits empty slots."""
        return [
            step_id
            for step_id in (self.primary_input_id, self.secondary_input_id)
            if step_id is not None
        ]


def _kind_of(node: StrategyStepNode) -> StepKind:
    if node.secondary_input is not None:
        return StepKind.COMBINE
    if node.primary_input is not None:
        return StepKind.TRANSFORM
    return StepKind.SEARCH


def own_search_name(node: StrategyStepNode, kind: StepKind) -> str | None:
    """The question this node names, or ``None`` when it names none.

    A combine carrying only the AST sentinel has no question of its own. A
    combine WDK named keeps that name.
    """
    if kind is StepKind.COMBINE and node.search_name == COMBINE_SEARCH_NAME:
        return None
    return node.search_name


class DuplicateStepIdError(ValueError):
    """The same step id occupies two positions in one tree."""


def flatten_tree(root: StrategyStepNode) -> dict[str, StrategyStep]:
    """Splits a nested node into a map of steps that reference each other by id.

    A repeated id is rejected. WDK requires a step to hold exactly one position.
    """
    steps: dict[str, StrategyStep] = {}

    def visit(node: StrategyStepNode) -> None:
        if node.id in steps:
            msg = (
                f"step id {node.id!r} appears twice in the tree; "
                f"every step must occupy exactly one position"
            )
            raise DuplicateStepIdError(msg)
        kind = _kind_of(node)
        steps[node.id] = StrategyStep(
            id=node.id,
            kind=kind,
            search_name=own_search_name(node, kind),
            parameters=dict(node.parameters),
            primary_input_id=node.primary_input_id,
            secondary_input_id=node.secondary_input_id,
            display_name=node.display_name,
            operator=node.operator,
            colocation_params=node.colocation_params,
            filters=list(node.filters),
            analyses=list(node.analyses),
            reports=list(node.reports),
            wdk_weight=node.wdk_weight,
            expanded_strategy_id=node.expanded_strategy_id,
            expanded_name=node.expanded_name,
        )
        for child in node.inputs():
            visit(child)

    visit(root)
    return steps


def rebuild_tree(root_id: str, steps: dict[str, StrategyStep]) -> StrategyStepNode:
    """Projects the keyed graph back to the nested shape WDK takes."""

    def visit(step_id: str) -> StrategyStepNode:
        step = steps[step_id]
        return StrategyStepNode(
            id=step.id,
            search_name=(
                COMBINE_SEARCH_NAME
                if step.kind is StepKind.COMBINE and step.search_name is None
                else step.search_name or ""
            ),
            parameters=dict(step.parameters),
            display_name=step.display_name,
            operator=step.operator,
            colocation_params=step.colocation_params,
            filters=list(step.filters),
            analyses=list(step.analyses),
            reports=list(step.reports),
            wdk_weight=step.wdk_weight,
            expanded_strategy_id=step.expanded_strategy_id,
            expanded_name=step.expanded_name,
            primary_input=(
                visit(step.primary_input_id)
                if step.primary_input_id is not None
                else None
            ),
            secondary_input=(
                visit(step.secondary_input_id)
                if step.secondary_input_id is not None
                else None
            ),
        )

    return visit(root_id)


def record_class_of(
    step_id: str, steps: dict[str, StrategyStep], *, fallback: str
) -> str:
    """The record class this step is addressed under.

    A combine states no search of its own, so it takes the class of the steps
    it consumes. The strategy's own class is the root's, which is what
    ``Strategy.getRecordClass`` returns.
    """
    return _own_or_inherited(step_id, steps, set()) or fallback


def _own_or_inherited(
    step_id: str, steps: dict[str, StrategyStep], seen: set[str]
) -> str | None:
    step = steps.get(step_id)
    if step is None or step_id in seen:
        return None
    seen.add(step_id)
    if step.record_class:
        return step.record_class
    for input_id in step.input_ids():
        inherited = _own_or_inherited(input_id, steps, seen)
        if inherited:
            return inherited
    return None


def wdk_search_name(step: StrategyStep) -> str:
    """The name this step reports outward. A combine has no question of its own,
    so this boundary supplies the placeholder; the push branches on the kind and
    creates a boolean step without it."""
    if step.kind is StepKind.COMBINE:
        return step.search_name or COMBINE_SEARCH_NAME
    return step.search_name or ""


def runs_a_wdk_search(step: StrategyStep) -> bool:
    """Reports whether this step names a question WDK can run.

    A combine names none, and neither does a combine that lost an input slot
    and now reads as a transform under the sentinel name.
    """
    name = wdk_search_name(step)
    return bool(name) and name != COMBINE_SEARCH_NAME


def is_computable(step: StrategyStep) -> bool:
    """Reports whether WDK can run this step. A combine needs both inputs and an
    operator, so a half-wired combine is a valid state that is not runnable."""
    if step.kind is not StepKind.COMBINE:
        return True
    return (
        step.primary_input_id is not None
        and step.secondary_input_id is not None
        and step.operator is not None
    )


def pushable_root_id(root_id: str, steps: dict[str, StrategyStep]) -> str | None:
    """Returns the deepest node WDK can compute, starting at the root. The walk passes
    a half-wired combine and continues to its remaining input."""
    current: str | None = root_id
    while current is not None:
        step = steps.get(current)
        if step is None:
            return None
        if is_computable(step):
            return current
        inputs = step.input_ids()
        current = inputs[0] if inputs else None
    return None
