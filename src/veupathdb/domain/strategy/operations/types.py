from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Discriminator, Field

from veupathdb.domain.parameters.values import ParamValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.ops import ColocationParams, CombineOp
from veupathdb.model import CamelModel


class DeleteResolution(StrEnum):
    COLLAPSE_COMBINE = "collapse-combine"
    ORPHAN_SIBLING = "orphan-sibling"
    DELETE_SUBTREE = "delete-subtree"
    PROMOTE_PRIMARY = "promote-primary"
    DELETE_STRATEGY = "delete-strategy"


class DeleteEdgeResolution(StrEnum):
    DETACH = "detach"
    COLLAPSE = "collapse"


class AttachNewRoot(CamelModel):
    mode: Literal["new-root"] = "new-root"


class AttachIntoSlot(CamelModel):
    mode: Literal["into-slot"] = "into-slot"
    target_step_id: str
    slot: Literal["primary", "secondary"]


AttachPoint = Annotated[
    AttachNewRoot | AttachIntoSlot,
    Discriminator("mode"),
]


class AddLeafOp(CamelModel):
    kind: Literal["addLeaf"] = "addLeaf"
    step: StrategyStepNode
    attach: AttachPoint


class AddCombineOp(CamelModel):
    kind: Literal["addCombine"] = "addCombine"
    step: StrategyStepNode
    left_id: str
    right_id: str


class AddTransformOp(CamelModel):
    kind: Literal["addTransform"] = "addTransform"
    step: StrategyStepNode
    input_id: str
    mode: Literal["before-consumer", "new-root"]


class DeleteStepOp(CamelModel):
    kind: Literal["deleteStep"] = "deleteStep"
    step_id: str
    resolution: DeleteResolution


class DeleteEdgeOp(CamelModel):
    """Remove one wire, addressed by the edge the canvas actually shows.

    ``delete_step`` addresses a node; the graph canvas addresses an edge.
    Keeping both endpoints lets the apply step reject a request built from a
    stale canvas rather than detaching whatever now occupies the slot.
    """

    kind: Literal["deleteEdge"] = "deleteEdge"
    source_id: str
    target_id: str
    slot: Literal["primary", "secondary"]
    resolution: DeleteEdgeResolution


class ReplaceSubtreeOp(CamelModel):
    kind: Literal["replaceSubtree"] = "replaceSubtree"
    step_id: str
    subtree: StrategyStepNode


class UpdateStepParamsOp(CamelModel):
    kind: Literal["updateStepParams"] = "updateStepParams"
    step_id: str
    parameters: dict[str, ParamValue]


class UpdateCombineOperatorOp(CamelModel):
    kind: Literal["updateCombineOperator"] = "updateCombineOperator"
    step_id: str
    operator: CombineOp
    colocation_params: ColocationParams | None = None


class UpdateStepMetaOp(CamelModel):
    kind: Literal["updateStepMeta"] = "updateStepMeta"
    step_id: str
    display_name: str


class UpdateStrategyMetaOp(CamelModel):
    kind: Literal["updateStrategyMeta"] = "updateStrategyMeta"
    name: str | None = None
    description: str | None = None


class DuplicateStepOp(CamelModel):
    kind: Literal["duplicateStep"] = "duplicateStep"
    source_step_id: str
    duplicate_step_id: str
    combine_step_id: str
    combine_display_name: str | None = None


class WireInputOp(CamelModel):
    kind: Literal["wireInput"] = "wireInput"
    target_step_id: str
    slot: Literal["primary", "secondary"]
    source_step_id: str


class ReplaceStrategyOp(CamelModel):
    """Whole-strategy replacement; used by undo/redo replay."""

    kind: Literal["replaceStrategy"] = "replaceStrategy"
    root: StrategyStepNode
    name: str | None = None
    description: str | None = None


GraphOperation = Annotated[
    AddLeafOp
    | AddCombineOp
    | AddTransformOp
    | DuplicateStepOp
    | DeleteStepOp
    | DeleteEdgeOp
    | ReplaceSubtreeOp
    | UpdateStepParamsOp
    | UpdateCombineOperatorOp
    | UpdateStepMetaOp
    | UpdateStrategyMetaOp
    | WireInputOp
    | ReplaceStrategyOp,
    Discriminator("kind"),
]


class OperationChoice(CamelModel):
    resolution: DeleteResolution
    title: str
    description: str
    is_default: bool
    will_delete: list[str] = Field(default_factory=list)
