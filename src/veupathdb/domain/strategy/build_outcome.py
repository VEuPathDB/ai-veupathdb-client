from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from veupathdb.model import CamelModel

NodeStatus = Literal["ok", "zero", "failed"]


def node_status(*, count: int | None, failed: bool) -> NodeStatus:
    if failed:
        return "failed"
    if count == 0:
        return "zero"
    return "ok"


class NodeResult(CamelModel):
    """Per-node build result surfaced to the Ledger/UI (BUILD's count feedback)."""

    node_id: str
    search_name: str
    wdk_step_id: int | None = None
    count: int | None = None
    status: NodeStatus
    error: str | None = None


@dataclass
class StepPushFailure:
    step_id: str
    search_name: str
    error: str


@dataclass
class BuildOutcome:
    """Structured result of a declarative strategy build."""

    pushed_step_ids: list[str] = field(default_factory=list)
    failed_steps: list[StepPushFailure] = field(default_factory=list)
    skipped_step_ids: list[str] = field(default_factory=list)
    wdk_strategy_id: int | None = None
    wdk_url: str | None = None
    counts: dict[str, int | None] = field(default_factory=dict)
    root_count: int | None = None
    zero_step_ids: list[str] = field(default_factory=list)
    node_results: list[NodeResult] = field(default_factory=list)

    @property
    def fully_succeeded(self) -> bool:
        return not self.failed_steps and not self.skipped_step_ids
