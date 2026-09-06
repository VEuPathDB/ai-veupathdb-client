"""Every strategy call addresses a concrete user id, and a step belongs to one
strategy.
"""

from __future__ import annotations

from typing import Any

import pytest

from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api import StrategyAPI


def _api(
    monkeypatch: pytest.MonkeyPatch, step_tree: dict[str, Any]
) -> tuple[StrategyAPI, list[str]]:
    client = VEuPathDBClient("https://example.invalid/service")
    paths: list[str] = []

    async def get(path: str, **_: object) -> Any:
        paths.append(path)
        return {"id": 4315616, "isGuest": False}

    async def post(path: str, **_: object) -> Any:
        paths.append(path)
        return {"stepTree": step_tree}

    monkeypatch.setattr(client, "get", get)
    monkeypatch.setattr(client, "post", post)
    return StrategyAPI(client), paths


async def test_wdk_http_001_a_later_call_carries_the_resolved_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, paths = _api(monkeypatch, {"stepId": 12})

    await api.get_duplicated_step_tree(9)

    assert paths == [
        "/users/current",
        "/users/4315616/strategies/9/duplicated-step-tree",
    ]


async def test_wdk_http_001_the_id_is_resolved_once_per_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, paths = _api(monkeypatch, {"stepId": 12})

    await api.get_duplicated_step_tree(9)
    await api.get_duplicated_step_tree(10)

    assert paths.count("/users/current") == 1


async def test_wdk_strat_007_reusing_a_branch_asks_for_new_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Two strategies cannot share a subtree, so reuse means copying.
    api, _ = _api(monkeypatch, {"stepId": 77, "primaryInput": {"stepId": 78}})

    tree = await api.get_duplicated_step_tree(9)

    assert tree.step_id == 77
    assert tree.primary_input is not None
    assert tree.primary_input.step_id == 78
