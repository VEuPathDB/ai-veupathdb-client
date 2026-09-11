"""The strategy and step rules, over the authoring graph and the client's writes."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest

from veupathdb.domain.strategy.graph_model import (
    StepKind,
    StrategyStep,
    pushable_root_id,
    record_class_of,
)
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.tree import root_ids, subtree_ids
from veupathdb.errors import WDKError
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import WDKStepTree

_IN_A_STRATEGY = "the step is part of a strategy"
_ALREADY_GONE = "no such step"

_STRATEGY: dict[str, Any] = {
    "strategyId": 5,
    "rootStepId": 3,
    "name": "demo",
    "isSaved": False,
    "isValid": True,
    "stepTree": {"stepId": 3},
    "steps": {},
}


def _leaf(step_id: str, record_class: str = "transcript") -> StrategyStep:
    return StrategyStep(
        id=step_id,
        kind=StepKind.SEARCH,
        search_name="GenesByMolecularWeight",
        record_class=record_class,
    )


def _half_wired_combine(step_id: str, primary: str) -> StrategyStep:
    return StrategyStep(
        id=step_id,
        kind=StepKind.COMBINE,
        primary_input_id=primary,
        operator=CombineOp.INTERSECT,
    )


def test_wdk_step_004_a_half_wired_combine_is_not_a_degraded_combine() -> None:
    """The push stops at the deepest step WDK can run, never at the empty combine."""
    steps = {"leaf": _leaf("leaf"), "combine": _half_wired_combine("combine", "leaf")}

    assert pushable_root_id("combine", steps) == "leaf"


def test_wdk_strat_002_a_strategy_has_exactly_one_root() -> None:
    """A second unconsumed step is a second root, which WDK cannot hold."""
    wired = {
        "a": _leaf("a"),
        "b": _leaf("b"),
        "combine": StrategyStep(
            id="combine",
            kind=StepKind.COMBINE,
            primary_input_id="a",
            secondary_input_id="b",
            operator=CombineOp.INTERSECT,
        ),
    }

    assert root_ids(wired) == {"combine"}
    assert root_ids({"a": _leaf("a"), "b": _leaf("b")}) == {"a", "b"}


def test_wdk_strat_003_every_step_a_strategy_holds_is_reachable_from_its_root() -> None:
    """The pushed subtree is the root and what feeds it, and nothing else."""
    steps = {
        "a": _leaf("a"),
        "b": _leaf("b"),
        "combine": StrategyStep(
            id="combine",
            kind=StepKind.COMBINE,
            primary_input_id="a",
            secondary_input_id="b",
            operator=CombineOp.UNION,
        ),
        "detached": _leaf("detached"),
    }

    assert sorted(subtree_ids("combine", steps)) == ["a", "b", "combine"]


def test_wdk_strat_004_the_strategy_takes_the_record_class_of_its_root() -> None:
    """A class-crossing transform makes the strategy its own class, not its leaf's."""
    steps = {
        "leaf": _leaf("leaf", record_class="transcript"),
        "transform": StrategyStep(
            id="transform",
            kind=StepKind.TRANSFORM,
            search_name="GenesByOrthologs",
            record_class="organism",
            primary_input_id="leaf",
        ),
    }

    assert record_class_of("transform", steps, fallback="transcript") == "organism"
    assert record_class_of("leaf", steps, fallback="organism") == "transcript"


async def test_wdk_strat_005_the_tree_write_is_followed_by_the_read_that_reports_validity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 204 says the tree is well-formed; only the strategy read says it runs."""
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    put_paths: list[str] = []
    read_paths: list[str] = []

    async def put(path: str, **_: object) -> None:
        put_paths.append(path)

    async def get(path: str, **_: object) -> Any:
        read_paths.append(path)
        return _STRATEGY

    monkeypatch.setattr(api.client, "put", put)
    monkeypatch.setattr(api.client, "get", get)

    details = await api.update_strategy(5, step_tree=WDKStepTree(stepId=3))

    assert put_paths == ["/users/1/strategies/5/step-tree"]
    assert read_paths == ["/users/1/strategies/5"]
    assert details.is_valid is True


async def test_wdk_step_007_a_conflict_on_delete_is_not_an_already_gone_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A step still in a tree answers 409, and only a 404 means already deleted."""
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")

    async def conflict(path: str, **_: object) -> None:
        del path
        raise WDKError(_IN_A_STRATEGY, status=HTTPStatus.CONFLICT)

    monkeypatch.setattr(api.client, "delete", conflict)

    with pytest.raises(WDKError) as caught:
        await api.delete_step(9)

    assert caught.value.status == HTTPStatus.CONFLICT


async def test_wdk_step_007_an_already_deleted_step_is_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def gone(path: str, **_: object) -> None:
        del path
        raise WDKError(_ALREADY_GONE, status=HTTPStatus.NOT_FOUND)

    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    monkeypatch.setattr(api.client, "delete", gone)

    assert await api.delete_step(9) is None
