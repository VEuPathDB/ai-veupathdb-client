"""A column distribution is asked of the step, and a refusal is not a fault.

The record-type document advertises byValue on thousands of columns that a step
will not accept it on, so a refusal there means "not on this search", not
"malformed".
"""

from __future__ import annotations

from typing import Any

import pytest

from veupathdb.errors import WDKError
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import WDKColumnDistribution


def _api(monkeypatch: pytest.MonkeyPatch) -> tuple[StrategyAPI, VEuPathDBClient]:
    client = VEuPathDBClient("https://example.invalid/service")

    async def get(path: str, **_: object) -> Any:
        del path
        return {"id": 4315616, "isGuest": False}

    monkeypatch.setattr(client, "get", get)
    return StrategyAPI(client), client


@pytest.mark.parametrize("status", [400, 500])
async def test_wdk_filter_006_a_refusal_is_not_treated_as_a_broken_request(
    status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, client = _api(monkeypatch)

    async def post(path: str, **_: object) -> Any:
        del path
        msg = 'column "primary_key" does not have have configured filter "byValue"'
        raise WDKError(msg, status=status)

    monkeypatch.setattr(client, "post", post)

    result = await api.get_column_distribution(440085983, "primary_key")

    assert result == WDKColumnDistribution()


async def test_wdk_filter_006_the_distribution_is_asked_of_the_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, client = _api(monkeypatch)
    paths: list[str] = []

    async def post(path: str, **_: object) -> Any:
        paths.append(path)
        return {"histogram": [], "statistics": {}}

    monkeypatch.setattr(client, "post", post)

    await api.get_column_distribution(440085983, "gene_product")

    assert paths == [
        "/users/4315616/steps/440085983/columns/gene_product/reports/byValue"
    ]
