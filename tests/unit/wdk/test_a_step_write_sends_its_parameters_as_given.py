from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from tests.unit.wdk._step_writes import Recorder

from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import NewStepSpec, WDKSearchConfig

_GIVEN = {
    "profile_pattern": "%pviv:Y%pfal:N%",
    "organism": '["Plasmodiidae"]',
    "retired": "a, b",
}
_SEARCH = "GenesByOrthologPattern"


def _api(monkeypatch: pytest.MonkeyPatch) -> tuple[StrategyAPI, Recorder, Recorder]:
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    post = Recorder(reply={"id": 41})
    put = Recorder()
    step = {
        "id": 9,
        "searchName": _SEARCH,
        "recordClassName": "transcript",
        "searchConfig": {"parameters": {}},
    }

    async def no_inputs(record_type: str, search_name: str, **_: object) -> Any:
        del record_type, search_name
        return SimpleNamespace(search_data=SimpleNamespace(parameters=[]))

    async def read_step(path: str, **_: object) -> Any:
        del path
        return step

    monkeypatch.setattr(api.client, "get_search_details", no_inputs)
    monkeypatch.setattr(api.client, "get", read_step)
    monkeypatch.setattr(api.client, "post", post)
    monkeypatch.setattr(api.client, "put", put)
    return api, post, put


async def test_a_new_step_sends_its_parameters_as_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, post, _put = _api(monkeypatch)

    await api.create_step(
        NewStepSpec(
            search_name=_SEARCH, search_config=WDKSearchConfig(parameters=_GIVEN)
        ),
        record_type="transcript",
        user_id="1",
    )

    assert post.body["searchConfig"]["parameters"] == _GIVEN


async def test_a_search_config_write_sends_its_parameters_as_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, _post, put = _api(monkeypatch)

    await api.update_step_search_config(
        9,
        WDKSearchConfig(parameters=_GIVEN),
        record_type="transcript",
        search_name=_SEARCH,
        user_id="1",
    )

    assert put.body["parameters"] == _GIVEN
