import re

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from veupathdb.wdk.search_load import SearchKind
from veupathdb.wdk.wdk_models import WDKIdentifier, WDKStepTree

_REMEMBERED = 10_000

_SEARCH_REPORT = re.compile(r"^/record-types/[^/]+/searches/([^/]+)/reports/[^/]+$")
_STEP = re.compile(r"^/users/[^/]+/steps/(\d+)(?:/|$)")
_STRATEGY = re.compile(r"^/users/[^/]+/strategies/(\d+)$")
_ANALYSIS_RUN = re.compile(r"/analyses/[^/]+/result$")
_NEW_STEP = re.compile(r"^/users/[^/]+/steps$")
_NEW_STRATEGY = re.compile(r"^/users/[^/]+/strategies$")
_NEW_TREE = re.compile(r"^/users/[^/]+/strategies/(\d+)/step-tree$")
_READ_STEP = re.compile(r"^/users/[^/]+/steps/(\d+)$")


class _NewStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    search_name: str = Field(alias="searchName")


class _NewTree(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_tree: WDKStepTree = Field(alias="stepTree")


class _ReadStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    search_name: str = Field(alias="searchName")


class _ReadStrategy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    strategy_id: int = Field(alias="strategyId")
    step_tree: WDKStepTree = Field(alias="stepTree")
    steps: dict[str, _ReadStep] = Field(default_factory=dict)


def search_kind(path: str) -> SearchKind:
    if _SEARCH_REPORT.match(path):
        return "report"
    if _STRATEGY.match(path):
        return "strategy"
    if _ANALYSIS_RUN.search(path):
        return "analysis"
    return "step"


def _remember[K, V](held: dict[K, V], key: K, value: V) -> None:
    held.pop(key, None)
    held[key] = value
    if len(held) > _REMEMBERED:
        del held[next(iter(held))]


class SearchNames:
    def __init__(self) -> None:
        self._names: dict[int, str] = {}
        self._inputs: dict[int, tuple[int, ...]] = {}
        self._roots: dict[int, int] = {}

    def of(self, path: str) -> frozenset[str]:
        if named := _SEARCH_REPORT.match(path):
            return frozenset({named.group(1)})
        if strategy := _STRATEGY.match(path):
            root = self._roots.get(int(strategy.group(1)))
            return frozenset() if root is None else self._tree_names(root)
        if step := _STEP.match(path):
            return self._tree_names(int(step.group(1)))
        return frozenset()

    def learn(self, method: str, path: str, body: object, answer: JsonValue) -> None:
        try:
            self._learn(method, path, body, answer)
        except ValidationError:
            return

    def _learn(self, method: str, path: str, body: object, answer: JsonValue) -> None:
        if method == "POST" and _NEW_STEP.match(path):
            step = WDKIdentifier.model_validate(answer).id
            _remember(self._names, step, _NewStep.model_validate(body).search_name)
        elif method == "POST" and _NEW_STRATEGY.match(path):
            strategy = WDKIdentifier.model_validate(answer).id
            self._learn_tree(strategy, _NewTree.model_validate(body).step_tree)
        elif method == "PUT" and (tree := _NEW_TREE.match(path)):
            self._learn_tree(
                int(tree.group(1)), _NewTree.model_validate(body).step_tree
            )
        elif method == "GET" and _READ_STEP.match(path):
            read = _ReadStep.model_validate(answer)
            _remember(self._names, read.id, read.search_name)
        elif method == "GET" and _STRATEGY.match(path):
            read_strategy = _ReadStrategy.model_validate(answer)
            for read_step in read_strategy.steps.values():
                _remember(self._names, read_step.id, read_step.search_name)
            self._learn_tree(read_strategy.strategy_id, read_strategy.step_tree)

    def _learn_tree(self, strategy: int, root: WDKStepTree) -> None:
        _remember(self._roots, strategy, root.step_id)
        pending = [root]
        while pending:
            node = pending.pop()
            inputs = [n for n in (node.primary_input, node.secondary_input) if n]
            _remember(self._inputs, node.step_id, tuple(n.step_id for n in inputs))
            pending.extend(inputs)

    def _tree_names(self, root: int) -> frozenset[str]:
        names: set[str] = set()
        seen: set[int] = set()
        pending = [root]
        while pending:
            step = pending.pop()
            if step in seen:
                continue
            seen.add(step)
            if step in self._names:
                names.add(self._names[step])
            pending.extend(self._inputs.get(step, ()))
        return frozenset(names)
