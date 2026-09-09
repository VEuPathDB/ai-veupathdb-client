"""Deleting orphaned step rows: every id is attempted, failures are reported."""

from __future__ import annotations

import pytest

from veupathdb.errors import WDKError
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI

_REFUSAL = "upstream refused"


def _api(
    monkeypatch: pytest.MonkeyPatch, fail_for: set[int]
) -> tuple[StrategyAPI, list[int]]:
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"))
    deleted: list[int] = []

    async def delete_step(step_id: int, *, user_id: str | None = None) -> None:
        del user_id
        if step_id in fail_for:
            raise WDKError(_REFUSAL, status=500)
        deleted.append(step_id)

    monkeypatch.setattr(api, "delete_step", delete_step)
    return api, deleted


async def test_no_ids_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    api, deleted = _api(monkeypatch, set())
    assert await api.delete_orphaned_steps([]) == []
    assert deleted == []


async def test_deletes_all_ids_in_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    api, deleted = _api(monkeypatch, set())
    assert await api.delete_orphaned_steps([10, 20, 30]) == []
    assert sorted(deleted) == [10, 20, 30]


async def test_returns_ids_that_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    api, deleted = _api(monkeypatch, {20})
    assert await api.delete_orphaned_steps([10, 20, 30]) == [20]
    assert sorted(deleted) == [10, 30]


async def test_every_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    api, deleted = _api(monkeypatch, {10, 20, 30})
    assert await api.delete_orphaned_steps([10, 20, 30]) == [10, 20, 30]
    assert deleted == []
