from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from tests.unit.wdk._step_writes import Recorder

from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.json_types import JSONObject
from veupathdb.wdk._searches import BooleanSearch
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import (
    CombinedStepSpec,
    NewStepSpec,
    WDKFilterValue,
    WDKSearchConfig,
)

_SEARCH = "GenesByTextSearch"
_PARAMETERS = {"text_expression": "kinase", "text_fields": "product"}
_MATCHED = WDKFilterValue(
    name="matched_transcript_filter_array", value={"values": ["Y"]}
)
_SENT_MATCHED = {
    "name": "matched_transcript_filter_array",
    "value": {"values": ["Y"]},
    "disabled": False,
}
_BOOLEAN = BooleanSearch(
    search_name="boolean_question_TranscriptRecordClasses_TranscriptRecordClass",
    left_param="bq_left_op_TranscriptRecordClasses_TranscriptRecordClass",
    right_param="bq_right_op_TranscriptRecordClasses_TranscriptRecordClass",
    operator_param="bq_operator",
)


def _api(
    monkeypatch: pytest.MonkeyPatch, held: dict[str, Any] | None = None
) -> tuple[StrategyAPI, Recorder, Recorder]:
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    post = Recorder(reply={"id": 41})
    put = Recorder()
    step = {
        "id": 9,
        "searchName": _SEARCH,
        "recordClassName": "transcript",
        "searchConfig": held or {"parameters": {}},
    }

    async def no_inputs(record_type: str, search_name: str, **_: object) -> Any:
        del record_type, search_name
        return SimpleNamespace(search_data=SimpleNamespace(parameters=[]))

    async def read_step(path: str, **_: object) -> Any:
        del path
        return step

    async def boolean(record_type: str) -> BooleanSearch:
        del record_type
        return _BOOLEAN

    monkeypatch.setattr(api.client, "get_search_details", no_inputs)
    monkeypatch.setattr(api.client, "boolean_search", boolean)
    monkeypatch.setattr(api.client, "get", read_step)
    monkeypatch.setattr(api.client, "post", post)
    monkeypatch.setattr(api.client, "put", put)
    return api, post, put


def _filtered_spec() -> NewStepSpec:
    return NewStepSpec(
        search_name=_SEARCH,
        search_config=WDKSearchConfig(
            parameters=_PARAMETERS, wdk_weight=10, filters=[_MATCHED]
        ),
    )


async def test_a_new_step_sends_its_filters_and_weight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, post, _put = _api(monkeypatch)

    await api.create_step(_filtered_spec(), "transcript", user_id="1")

    assert post.body["searchConfig"]["filters"] == [_SENT_MATCHED]
    assert post.body["searchConfig"]["wdkWeight"] == 10
    assert post.body["searchConfig"]["parameters"] == _PARAMETERS


async def test_a_new_step_sends_its_column_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, post, _put = _api(monkeypatch)
    column_filters: JSONObject = {"gene_product": {"byValue": {"pattern": "kinase"}}}

    await api.create_step(
        NewStepSpec(
            search_name=_SEARCH,
            search_config=WDKSearchConfig(
                parameters=_PARAMETERS, column_filters=column_filters
            ),
        ),
        "transcript",
        user_id="1",
    )

    assert post.body["searchConfig"]["columnFilters"] == column_filters


async def test_a_new_transform_step_sends_its_filters_and_weight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, post, _put = _api(monkeypatch)

    await api.create_transform_step(_filtered_spec(), 5, "transcript", user_id="1")

    assert post.body["searchConfig"]["filters"] == [_SENT_MATCHED]
    assert post.body["searchConfig"]["wdkWeight"] == 10


async def test_a_new_combined_step_sends_its_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, post, _put = _api(monkeypatch)

    await api.create_combined_step(
        CombinedStepSpec(
            primary_step_id=1,
            secondary_step_id=2,
            boolean_operator=CombineOp.INTERSECT,
            filters=[_MATCHED],
        ),
        "transcript",
        user_id="1",
    )

    assert post.body["searchName"] == _BOOLEAN.search_name
    assert post.body["searchConfig"]["filters"] == [_SENT_MATCHED]
    assert post.body["searchConfig"]["parameters"] == {
        _BOOLEAN.left_param: "",
        _BOOLEAN.right_param: "",
        _BOOLEAN.operator_param: "INTERSECT",
    }


async def test_a_combined_step_without_filters_sends_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, post, _put = _api(monkeypatch)

    await api.create_combined_step(
        CombinedStepSpec(
            primary_step_id=1, secondary_step_id=2, boolean_operator=CombineOp.UNION
        ),
        "transcript",
        user_id="1",
    )

    assert "filters" not in post.body["searchConfig"]
    assert "wdkWeight" not in post.body["searchConfig"]


async def test_a_search_config_write_that_states_no_filters_sends_an_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, _post, put = _api(monkeypatch, {"parameters": {}, "filters": [_SENT_MATCHED]})

    await api.update_step_search_config(
        9,
        WDKSearchConfig(parameters=_PARAMETERS, filters=[]),
        record_type="transcript",
        search_name=_SEARCH,
        user_id="1",
    )

    assert put.body["filters"] == []


async def test_a_search_config_write_that_states_filters_sends_exactly_those(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = {"name": "gene_boolean_filter_array", "value": {"values": ["YY"]}}
    api, _post, put = _api(monkeypatch, {"parameters": {}, "filters": [held]})

    await api.update_step_search_config(
        9,
        WDKSearchConfig(parameters=_PARAMETERS, filters=[_MATCHED]),
        record_type="transcript",
        search_name=_SEARCH,
        user_id="1",
    )

    assert put.body["filters"] == [_SENT_MATCHED]


async def test_a_search_config_write_that_states_no_filter_list_keeps_the_held_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, _post, put = _api(monkeypatch, {"parameters": {}, "filters": [_SENT_MATCHED]})

    await api.update_step_search_config(
        9,
        WDKSearchConfig(parameters=_PARAMETERS),
        record_type="transcript",
        search_name=_SEARCH,
        user_id="1",
    )

    assert put.body["filters"] == [_SENT_MATCHED]
