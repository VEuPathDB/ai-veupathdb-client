from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from tests.unit.wdk._step_writes import Recorder

from veupathdb.domain.parameters.phyletic import sort_profile_pattern
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import NewStepSpec, WDKSearchConfig

_PATTERN = "%pviv:Y%pfal:N%"
_GIVEN = {
    "profile_pattern": _PATTERN,
    "organism": '["Plasmodiidae"]',
    "retired": "a, b",
}
_SEARCH = "GenesByOrthologPattern"


def _api(monkeypatch: pytest.MonkeyPatch) -> tuple[StrategyAPI, Recorder, list[Any]]:
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    post = Recorder(reply={"id": 41})
    shaped: list[dict[str, str]] = []

    async def no_inputs(record_type: str, search_name: str, **_: object) -> Any:
        del record_type, search_name
        return SimpleNamespace(search_data=SimpleNamespace(parameters=[]))

    async def leaves(
        record_type: str, search_name: str, params: dict[str, str]
    ) -> dict[str, str]:
        del record_type, search_name
        shaped.append(dict(params))
        return {
            name: '["leaf"]' if name == "organism" else value
            for name, value in params.items()
        }

    async def same_codes(record_type: str, pattern: str) -> str:
        del record_type
        return pattern

    monkeypatch.setattr(api.client, "get_search_details", no_inputs)
    monkeypatch.setattr(api.client, "expand_tree_params_to_leaves", leaves)
    monkeypatch.setattr(api.client, "post", post)
    monkeypatch.setattr(api, "_expand_profile_pattern_groups", same_codes)
    return api, post, shaped


async def _create(api: StrategyAPI, verbatim: set[str]) -> None:
    await api.create_step(
        NewStepSpec(
            search_name=_SEARCH, search_config=WDKSearchConfig(parameters=_GIVEN)
        ),
        record_type="transcript",
        user_id="1",
        verbatim=verbatim,
    )


async def test_a_verbatim_value_goes_out_as_given_and_is_never_shaped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, post, shaped = _api(monkeypatch)

    await _create(api, set(_GIVEN))

    assert post.body["searchConfig"]["parameters"] == _GIVEN
    assert shaped == [{}]


async def test_a_stated_value_is_shaped_beside_a_verbatim_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, post, shaped = _api(monkeypatch)

    await _create(api, {"retired"})

    assert post.body["searchConfig"]["parameters"] == {
        "profile_pattern": sort_profile_pattern(_PATTERN),
        "organism": '["leaf"]',
        "retired": "a, b",
    }
    assert [sorted(s) for s in shaped] == [["organism", "profile_pattern"]]


async def test_a_search_config_write_keeps_a_verbatim_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, _post, shaped = _api(monkeypatch)
    put = Recorder()
    step = {
        "id": 9,
        "searchName": _SEARCH,
        "recordClassName": "transcript",
        "searchConfig": {"parameters": {}},
    }

    async def read_step(path: str, **_: object) -> Any:
        del path
        return step

    monkeypatch.setattr(api.client, "get", read_step)
    monkeypatch.setattr(api.client, "put", put)

    await api.update_step_search_config(
        9,
        WDKSearchConfig(parameters=_GIVEN),
        record_type="transcript",
        search_name=_SEARCH,
        user_id="1",
        verbatim={"organism", "profile_pattern"},
    )

    assert put.body["parameters"] == {
        "profile_pattern": _PATTERN,
        "organism": '["Plasmodiidae"]',
        "retired": "a, b",
    }
    assert shaped == [{"retired": "a, b"}]
