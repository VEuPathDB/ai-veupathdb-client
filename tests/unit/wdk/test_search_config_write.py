"""A search-config write starts from the step's own config (WDK-STEP-003).

The endpoint resets every key the body omits and refuses a changed input value,
so a write that cannot carry every input value never reaches WDK.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from tests.unit.wdk._step_writes import Recorder, no_expansion

from veupathdb.errors import DataParsingError, WDKError
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import WDKSearchConfig
from veupathdb.wdk.wdk_parameters import (
    WDKAnswerParam,
    WDKParameter,
    WDKStringParam,
)

_ALWAYS_APPLIED = "matched_transcript_filter_array"


def _held_step_api(
    monkeypatch: pytest.MonkeyPatch,
    held: dict[str, Any],
    params: list[WDKParameter] | None = None,
) -> tuple[StrategyAPI, Recorder]:
    """A step that holds ``held`` as its search config, under a search of ``params``."""
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    put = Recorder()
    monkeypatch.setattr(api.client, "put", put)
    monkeypatch.setattr(api, "_expand_tree_params_to_leaves", no_expansion)

    async def details(record_type: str, search_name: str, **_: object) -> Any:
        del record_type, search_name
        return SimpleNamespace(search_data=SimpleNamespace(parameters=params or []))

    async def read_step(path: str, **_: object) -> Any:
        del path
        return {"id": 9, "searchName": "GenesByOrthologs", "searchConfig": held}

    monkeypatch.setattr(api.client, "get_search_details", details)
    monkeypatch.setattr(api.client, "get", read_step)
    return api, put


async def _write(api: StrategyAPI, config: WDKSearchConfig) -> None:
    await api.update_step_search_config(
        9,
        config,
        record_type="transcript",
        search_name="GenesByOrthologs",
        user_id="1",
    )


class TestAWriteRefusesWhatWDKWouldRefuse:
    """WDK-STEP-003: a write that cannot carry every input value never reaches WDK."""

    async def test_a_failed_catalog_read_stops_the_write(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _held_step_api(monkeypatch, {"parameters": {"gene_result": "5"}})

        async def unavailable(record_type: str, search_name: str, **_: object) -> Any:
            msg = f"GET /record-types/{record_type}/searches/{search_name} -> HTTP 503"
            raise WDKError(msg, status=503)

        monkeypatch.setattr(api.client, "get_search_details", unavailable)

        with pytest.raises(WDKError, match="GenesByOrthologs"):
            await _write(api, WDKSearchConfig(parameters={"isSyntenic": "yes"}))
        assert put.bodies == []

    async def test_a_step_without_its_input_value_stops_the_write(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _held_step_api(
            monkeypatch,
            {"parameters": {"isSyntenic": "no"}},
            [WDKAnswerParam(name="gene_result"), WDKStringParam(name="isSyntenic")],
        )

        with pytest.raises(DataParsingError, match=r"step 9.*gene_result"):
            await _write(api, WDKSearchConfig(parameters={"isSyntenic": "yes"}))
        assert put.bodies == []


class TestAWriteStartsFromTheStepsOwnConfig:
    """WDK-STEP-003: every key the caller does not change goes back as the step holds it."""

    async def test_the_steps_weight_is_kept_when_the_caller_states_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _held_step_api(monkeypatch, {"parameters": {}, "wdkWeight": 5})

        await _write(api, WDKSearchConfig(parameters={"isSyntenic": "yes"}))

        assert put.body["wdkWeight"] == 5

    async def test_a_stated_weight_replaces_the_steps_own(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _held_step_api(monkeypatch, {"parameters": {}, "wdkWeight": 5})

        await _write(api, WDKSearchConfig(parameters={}, wdk_weight=7))

        assert put.body["wdkWeight"] == 7

    async def test_a_stated_zero_weight_is_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _held_step_api(monkeypatch, {"parameters": {}, "wdkWeight": 5})

        await _write(api, WDKSearchConfig(parameters={}, wdk_weight=0))

        assert put.body["wdkWeight"] == 0

    async def test_the_steps_column_filters_go_back_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        column_filters = {"gene_product": {"byValue": {"pattern": "kinase"}}}
        api, put = _held_step_api(
            monkeypatch, {"parameters": {}, "columnFilters": column_filters}
        )

        await _write(api, WDKSearchConfig(parameters={"isSyntenic": "yes"}))

        assert put.body["columnFilters"] == column_filters

    async def test_the_steps_filters_go_back_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        held = {"name": _ALWAYS_APPLIED, "disabled": True, "value": {"values": ["Y"]}}
        api, put = _held_step_api(monkeypatch, {"parameters": {}, "filters": [held]})

        await _write(api, WDKSearchConfig(parameters={"isSyntenic": "yes"}))

        assert put.body["filters"] == [held]

    async def test_a_search_without_parameters_still_sends_the_object(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _held_step_api(monkeypatch, {"parameters": {}})

        await _write(api, WDKSearchConfig())

        assert put.body["parameters"] == {}

    async def test_the_view_filters_never_reach_the_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _held_step_api(
            monkeypatch, {"parameters": {}, "viewFilters": [{"name": "v"}]}
        )

        await _write(api, WDKSearchConfig(parameters={"isSyntenic": "yes"}))

        assert "viewFilters" not in put.body
