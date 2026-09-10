"""The canonical typed representation of a strategy graph.

A pushed strategy has one root step, which matches the WDK step tree shape.
"""

from pydantic import Field, model_validator

from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.tree import walk
from veupathdb.domain.strategy.validation import StepValidation
from veupathdb.json_types import JSONObject
from veupathdb.model import CamelModel


class StrategyAst(CamelModel):
    """Serialized strategy graph state used at every persistence boundary."""

    record_type: str
    root: StrategyStepNode
    detached_roots: list[StrategyStepNode] = Field(default_factory=list)
    """Components that the root cannot reach. WDK holds no step with inputs
    outside a strategy, so these stay here and the push planner walks the root only.
    """

    name: str | None = None
    description: str | None = None
    metadata: JSONObject | None = None
    step_counts: dict[str, int] | None = None
    wdk_step_ids: dict[str, int] | None = None
    step_validations: dict[str, StepValidation] | None = None
    wdk_push_errors: dict[str, str] | None = None
    """Why WDK rejected a step. The rejection belongs to the step, not to the commit."""

    @model_validator(mode="after")
    def _validate_single_root_and_unique_ids(self) -> "StrategyAst":
        """Reject duplicate step ids anywhere in the graph.

        A step belongs to one position only, so the detached components count too.
        """
        nodes = list(walk(self.root))
        for detached in self.detached_roots:
            nodes.extend(walk(detached))
        seen: set[str] = set()
        duplicates: set[str] = set()
        for node in nodes:
            if node.id in seen:
                duplicates.add(node.id)
            seen.add(node.id)
        if duplicates:
            msg = (
                f"strategy contains duplicate step ids: {sorted(duplicates)}; "
                "every step in the tree must have a unique id"
            )
            raise ValueError(msg)
        return self
