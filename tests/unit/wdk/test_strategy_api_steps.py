"""What a step write may change, and what it must leave alone.

A filter WDK applies by itself survives every write of a search config:
omitting the filters array does not remove such a filter, WDK puts it back
enabled, and the write answers 204 either way. A new leaf step's answer
parameters must go out as ``""``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import (
    WDKSearch,
    WDKSearchConfig,
    WDKSearchResponse,
)
from veupathdb.wdk.wdk_parameters import (
    WDKAnswerParam,
    WDKParameter,
    WDKStringParam,
)

_ALWAYS_APPLIED = "matched_transcript_filter_array"

_STEP: dict[str, Any] = {
    "id": 9,
    "searchName": "GenesByMolecularWeight",
    "recordClassName": "transcript",
    "isFiltered": False,
    "searchConfig": {
        "parameters": {"min_molecular_weight": "10000"},
        "filters": [
            {"name": _ALWAYS_APPLIED, "disabled": True, "value": {"values": ["Y"]}}
        ],
        "wdkWeight": 0,
    },
}


class _Recorder:
    """Captures a request body instead of reaching WDK."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> Any:
        del path
        self.bodies.append(json or {})
        return None

    @property
    def body(self) -> dict[str, Any]:
        return self.bodies[-1]


async def _read_step(path: str, **_: object) -> Any:
    del path
    return _STEP


async def _no_expansion(
    record_type: str, search_name: str, params: dict[str, str]
) -> dict[str, str]:
    del record_type, search_name
    return params


def _api(monkeypatch: pytest.MonkeyPatch) -> tuple[StrategyAPI, _Recorder]:
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    put = _Recorder()
    monkeypatch.setattr(api.client, "get", _read_step)
    monkeypatch.setattr(api.client, "put", put)
    monkeypatch.setattr(api, "_expand_tree_params_to_leaves", _no_expansion)
    return api, put


def _api_with_params(
    monkeypatch: pytest.MonkeyPatch, params: list[WDKParameter]
) -> StrategyAPI:
    client = VEuPathDBClient("https://example.invalid/service")

    async def details(record_type: str, search_name: str, **_: object) -> Any:
        del record_type, search_name
        return SimpleNamespace(search_data=SimpleNamespace(parameters=params))

    monkeypatch.setattr(client, "get_search_details", details)
    return StrategyAPI(client)


async def _update(api: StrategyAPI, weight: int = 0) -> None:
    await api.update_step_search_config(
        9,
        WDKSearchConfig(
            parameters={"min_molecular_weight": "20000"}, wdk_weight=weight
        ),
        record_type="transcript",
        search_name="GenesByMolecularWeight",
        user_id="1",
    )


class TestAWriteKeepsTheFiltersItDidNotSet:
    async def test_the_filters_array_is_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _api(monkeypatch)

        await _update(api)

        assert "filters" in put.body

    async def test_a_disabled_filter_stays_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Omitting it would let WDK re-inject the filter enabled, which changes
        # the count without changing anything the caller asked about.
        api, put = _api(monkeypatch)

        await _update(api)

        sent = {f["name"]: f for f in put.body["filters"]}
        assert sent[_ALWAYS_APPLIED]["disabled"] is True

    async def test_the_filter_value_survives_the_round_trip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _api(monkeypatch)

        await _update(api)

        sent = {f["name"]: f for f in put.body["filters"]}
        assert sent[_ALWAYS_APPLIED]["value"] == {"values": ["Y"]}

    async def test_the_new_parameters_still_reach_wdk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _api(monkeypatch)

        await _update(api)

        assert put.body["parameters"]["min_molecular_weight"] == "20000"


class TestSettingAFilterIsHowItIsTurnedOff:
    async def test_disabling_is_written_rather_than_omitted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _api(monkeypatch)

        await api.set_step_filter(
            9, _ALWAYS_APPLIED, {"values": ["Y"]}, disabled=True, user_id="1"
        )

        sent = {f["name"]: f for f in put.body["filters"]}
        assert sent[_ALWAYS_APPLIED]["disabled"] is True

    async def test_an_unrelated_filter_is_not_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api, put = _api(monkeypatch)

        await api.set_step_filter(9, "other_filter", {"values": ["N"]}, user_id="1")

        assert {f["name"] for f in put.body["filters"]} == {
            _ALWAYS_APPLIED,
            "other_filter",
        }


class TestANewStepSendsItsAnswerParamsEmpty:
    """``AnswerParam.java``: the value is the empty string or a step id, and for
    a brand-new step it is ``""``. The real input is wired via the stepTree.
    """

    async def test_empty_answer_params_forces_input_step_params_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api_with_params(
            monkeypatch,
            [
                WDKAnswerParam(name="gene_result"),
                WDKStringParam(name="MinPercentMinorAlleles"),
            ],
        )

        out = await api._empty_answer_params(
            "transcript",
            "GenesByOrthologs",
            {"organism": '["Toxoplasma gondii ME49"]', "gene_result": "999"},
        )

        assert out["gene_result"] == ""
        assert out["organism"] == '["Toxoplasma gondii ME49"]'

    async def test_empty_answer_params_noop_without_answer_params(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _api_with_params(monkeypatch, [WDKStringParam(name="x")])

        out = await api._empty_answer_params(
            "transcript", "GenesByText", {"x": "kinase"}
        )

        assert out == {"x": "kinase"}


async def test_wdk_step_006_the_names_are_read_from_the_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = VEuPathDBClient("https://example.invalid/service")
    api = StrategyAPI(client)
    recorded = WDKSearchResponse.model_validate(
        load_recorded("search_boolean_transcript").json_body()
    )

    async def details(record_type: str, search_name: str, **_: object) -> Any:
        del record_type, search_name
        return recorded

    async def searches(record_type: str) -> list[WDKSearch]:
        del record_type
        return [recorded.search_data]

    monkeypatch.setattr(client, "get_search_details", details)
    monkeypatch.setattr(client, "get_searches", searches)

    left, right, operator = await api._get_boolean_param_names("transcript")

    assert left == "bq_left_op_TranscriptRecordClasses_TranscriptRecordClass"
    assert right == "bq_right_op_TranscriptRecordClasses_TranscriptRecordClass"
    assert operator == "bq_operator"
