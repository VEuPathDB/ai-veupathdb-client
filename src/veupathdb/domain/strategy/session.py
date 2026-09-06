"""In-memory working state for a strategy that is under construction during a
chat session."""

from veupathdb.domain.strategy.graph_model import StrategyStep, rebuild_tree
from veupathdb.domain.strategy.strategy_ast import StrategyAst
from veupathdb.domain.strategy.tree import parent_of, root_ids, subtree_ids
from veupathdb.domain.strategy.types import SyncStateProtocol
from veupathdb.domain.strategy.validation import StepValidation
from veupathdb.logging import get_logger
from veupathdb.model import CamelModel

logger = get_logger(__name__)


class StrategyHistoryEntry(CamelModel):
    """One undo history entry. The history is transient and rebuilds on load."""

    description: str
    strategy_ast: StrategyAst


class StrategyGraph:
    """State for a single strategy graph."""

    def __init__(self, graph_id: str, name: str, site_id: str) -> None:
        self.id = graph_id
        self.name = name
        self.site_id = site_id
        # The record type is set on the first step or on import of a strategy.
        self.record_type: str | None = None
        self.description: str | None = None
        self.steps: dict[str, StrategyStep] = {}
        # A root is a step that no other step consumes. A complete strategy has
        # exactly one root.
        self.roots: set[str] = set()
        self.history: list[StrategyHistoryEntry] = []
        self.last_step_id: str | None = None

    def primary_root_id(self) -> str | None:
        """Return the root of the main strategy tree.

        The largest subtree wins. A tie goes to the step that was added first,
        so the result is stable across calls.
        """
        if not self.roots:
            return None
        if len(self.roots) == 1:
            return next(iter(self.roots))
        ordered = [sid for sid in self.steps if sid in self.roots]
        return max(
            ordered,
            key=lambda sid: (self.subtree_size(sid), -ordered.index(sid)),
        )

    def subtree_size(self, step_id: str) -> int:
        return len(subtree_ids(step_id, self.steps))

    def to_strategy_ast(
        self,
        root_step_id: str | None = None,
        sync_state: SyncStateProtocol | None = None,
        *,
        include_detached: bool = True,
    ) -> StrategyAst | None:
        """Produce a typed plan payload for API responses and persistence.

        With ``include_detached=False`` the payload holds only the subtree
        under the root, which is the shape WDK accepts.
        """
        root_id = root_step_id or self.primary_root_id()
        if root_id is None or root_id not in self.steps:
            return None
        root = rebuild_tree(root_id, self.steps)
        detached = (
            [
                rebuild_tree(sid, self.steps)
                for sid in self.steps
                if sid in self.roots and sid != root_id
            ]
            if include_detached
            else []
        )

        step_counts: dict[str, int] | None = None
        wdk_step_ids: dict[str, int] | None = None
        step_validations: dict[str, StepValidation] | None = None
        wdk_push_errors: dict[str, str] | None = None
        if sync_state is not None:
            if sync_state.step_counts:
                step_counts = {
                    k: v for k, v in sync_state.step_counts.items() if v is not None
                }
            if sync_state.wdk_step_ids:
                wdk_step_ids = dict(sync_state.wdk_step_ids)
            if sync_state.step_validations:
                step_validations = dict(sync_state.step_validations)
            if sync_state.wdk_push_errors:
                wdk_push_errors = dict(sync_state.wdk_push_errors)

        return StrategyAst(
            record_type=self.record_type or "",
            root=root,
            detached_roots=detached,
            name=self.name,
            description=self.description or None,
            step_counts=step_counts,
            wdk_step_ids=wdk_step_ids,
            step_validations=step_validations,
            wdk_push_errors=wdk_push_errors,
        )

    def parent_of(self, step_id: str) -> tuple[StrategyStep, str] | None:
        """Return the parent of a step and the input slot it occupies, or
        ``None`` when the step is a root or is absent."""
        return parent_of(step_id, self.steps)

    def get_step(self, step_id: str) -> StrategyStep | None:
        return self.steps.get(step_id)

    def recompute_roots(self) -> None:
        """Recompute the root set from the current steps. Call this after a
        bulk mutation such as a delete or a hydration."""
        self.roots = root_ids(self.steps)

    def save_history(self, description: str) -> None:
        """Save current state to history."""
        ast = self.to_strategy_ast()
        if ast is not None:
            self.history.append(
                StrategyHistoryEntry(description=description, strategy_ast=ast),
            )


class StrategySession:
    """Session context for the active strategy (graph + chat)."""

    def __init__(self, site_id: str) -> None:
        self.site_id = site_id
        self.graph: StrategyGraph | None = None
        self.sync_state: SyncStateProtocol | None = None

    def add_graph(self, graph: StrategyGraph) -> None:
        """Register a graph in the session. A session holds one graph, so a
        second, different graph is ignored."""
        if self.graph and self.graph.id != graph.id:
            logger.warning(
                "Ignoring add_graph: session already has an active graph",
                active_graph_id=self.graph.id,
                rejected_graph_id=graph.id,
            )
            return
        self.graph = graph

    def get_graph(self, graph_id: str | None) -> StrategyGraph | None:
        """Return the graph with this id, or the active graph when the id is
        ``None``."""
        if not self.graph:
            return None
        if graph_id is None or graph_id == self.graph.id:
            return self.graph
        return None
