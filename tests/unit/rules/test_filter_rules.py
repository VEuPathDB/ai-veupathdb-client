"""WDK-FILTER-001, WDK-FILTER-003 and WDK-STEP-003 over the search config this client writes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import WDKSearchConfig
from veupathdb.wdk.wdk_parameters import WDKAnswerParam

_ALWAYS_APPLIED = "matched_transcript_filter_array"

_STEP: dict[str, Any] = {
    "id": 9,
    "searchName": "GenesByMolecularWeight",
    "recordClassName": "transcript",
    "searchConfig": {
        "parameters": {"min_molecular_weight": "10000", "gene_result": "77"},
        "filters": [{"name": _ALWAYS_APPLIED, "disabled": False}],
        "columnFilters": {"gene_product": {"byValue": {"pattern": "kinase"}}},
        "viewFilters": [{"name": "a_view_filter"}],
        "wdkWeight": 0,
    },
}


class _Written:
    """Keeps the body of the one search-config write."""

    def __init__(self) -> None:
        self.body: dict[str, Any] = {}

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> None:
        del path
        self.body = json or {}


async def _read_step(path: str, **_: object) -> Any:
    del path
    return _STEP


def _client(monkeypatch: pytest.MonkeyPatch) -> tuple[VEuPathDBClient, _Written]:
    client = VEuPathDBClient("https://example.invalid/service")
    written = _Written()
    monkeypatch.setattr(client, "get", _read_step)
    monkeypatch.setattr(client, "put", written)
    return client, written


def test_wdk_filter_001_the_search_config_keeps_the_three_mechanisms_apart() -> None:
    """A `filter` parameter, `filters` and `columnFilters` are three fields."""
    config = WDKSearchConfig.model_validate(_STEP["searchConfig"])
    written = config.model_dump(by_alias=True, exclude_none=True)

    assert written["parameters"]["min_molecular_weight"] == "10000"
    assert [entry["name"] for entry in written["filters"]] == [_ALWAYS_APPLIED]
    assert written["columnFilters"] == {
        "gene_product": {"byValue": {"pattern": "kinase"}}
    }


async def test_wdk_filter_003_a_search_config_write_carries_no_view_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`viewFilters` inside a search config is a 400, so the write drops it."""
    client, written = _client(monkeypatch)

    await StrategyAPI(client, "1").set_step_filter(9, _ALWAYS_APPLIED, None)

    assert "viewFilters" not in written.body
    assert [entry["name"] for entry in written.body["filters"]] == [_ALWAYS_APPLIED]


async def test_wdk_step_003_a_search_config_write_keeps_the_answer_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The endpoint cannot change a step's inputs, so the write sends them back."""
    client, written = _client(monkeypatch)
    api = StrategyAPI(client, "1")

    async def inputs(record_type: str, search_name: str, **_: object) -> Any:
        del record_type, search_name
        return SimpleNamespace(
            search_data=SimpleNamespace(parameters=[WDKAnswerParam(name="gene_result")])
        )

    monkeypatch.setattr(client, "get_search_details", inputs)

    await api.set_step_filter(9, _ALWAYS_APPLIED, None)
    after_filter = written.body["parameters"]["gene_result"]
    await api.update_step_search_config(
        9,
        WDKSearchConfig(parameters={"min_molecular_weight": "20000"}),
        record_type="transcript",
        search_name="GenesByMolecularWeight",
    )

    assert after_filter == "77"
    assert written.body["parameters"] == {
        "min_molecular_weight": "20000",
        "gene_result": "77",
    }
