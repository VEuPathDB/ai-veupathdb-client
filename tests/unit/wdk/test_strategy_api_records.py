"""A column distribution is asked of the step, and a failed report raises."""

from __future__ import annotations

from typing import Any

import pytest

from veupathdb.errors import DataParsingError, WDKError
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI


def _api(monkeypatch: pytest.MonkeyPatch) -> tuple[StrategyAPI, VEuPathDBClient]:
    client = VEuPathDBClient("https://example.invalid/service")

    async def get(path: str, **_: object) -> Any:
        del path
        return {"id": 1000000104, "isGuest": False}

    monkeypatch.setattr(client, "get", get)
    return StrategyAPI(client), client


@pytest.mark.parametrize("status", [400, 500])
async def test_wdk_filter_006_a_refusal_raises_with_its_status(
    status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, client = _api(monkeypatch)

    async def post(path: str, **_: object) -> Any:
        del path
        msg = 'column "primary_key" does not have have configured filter "byValue"'
        raise WDKError(msg, status=status)

    monkeypatch.setattr(client, "post", post)

    with pytest.raises(WDKError) as refused:
        await api.get_column_distribution(900000001, "primary_key")

    assert refused.value.status == status


async def test_an_unparseable_report_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    api, client = _api(monkeypatch)

    async def post(path: str, **_: object) -> Any:
        del path
        return {"histogram": [{"value": "many"}], "statistics": {}}

    monkeypatch.setattr(client, "post", post)

    with pytest.raises(DataParsingError, match="gene_product"):
        await api.get_column_distribution(900000001, "gene_product")


async def test_wdk_filter_006_the_distribution_is_asked_of_the_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, client = _api(monkeypatch)
    sent: list[tuple[str, object, object]] = []

    async def post(path: str, **kwargs: object) -> Any:
        sent.append((path, kwargs["json"], kwargs["budget_seconds"]))
        return {
            "histogram": [
                {
                    "value": 412,
                    "binStart": "kinase",
                    "binEnd": "kinase",
                    "binLabel": "kinase",
                }
            ],
            "statistics": {
                "subsetSize": 430,
                "numVarValues": 412,
                "numDistinctValues": 1,
                "numDistinctEntityRecords": 412,
                "numMissingCases": 18,
            },
        }

    monkeypatch.setattr(client, "post", post)

    distribution = await api.get_column_distribution(
        900000001, "gene_product", budget_seconds=45.0
    )

    assert sent == [
        (
            "/users/1000000104/steps/900000001/columns/gene_product/reports/byValue",
            {"reportConfig": {}},
            45.0,
        )
    ]
    assert [(b.bin_label, b.value) for b in distribution.histogram] == [("kinase", 412)]
    assert (
        distribution.statistics.subset_size,
        distribution.statistics.num_missing_cases,
    ) == (430, 18)
