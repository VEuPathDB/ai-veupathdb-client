"""A step report carries its view filters beside the report config (WDK-FILTER-003)."""

from __future__ import annotations

import pytest
from tests.unit.wdk._step_writes import Recorder

from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import WDKFilterValue

_ONE_PER_GENE = WDKFilterValue(name="representativeTranscriptOnly", value={})
_PAGE = {"offset": 0, "numRecords": 10}


def _api(monkeypatch: pytest.MonkeyPatch) -> tuple[StrategyAPI, Recorder]:
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    report = Recorder(
        reply=load_recorded("answer_report_by_molecular_weight").json_body()
    )
    monkeypatch.setattr(api.client, "post", report)
    return api, report


async def test_the_view_filters_sit_beside_the_report_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, report = _api(monkeypatch)

    await api.get_step_records(9, pagination=_PAGE, view_filters=[_ONE_PER_GENE])

    assert report.body == {
        "reportConfig": {"pagination": _PAGE},
        "viewFilters": [
            {"name": "representativeTranscriptOnly", "value": {}, "disabled": False}
        ],
    }


async def test_an_answer_read_passes_its_view_filters_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, report = _api(monkeypatch)

    await api.get_step_answer(9, pagination=_PAGE, view_filters=[_ONE_PER_GENE])

    assert [f["name"] for f in report.body["viewFilters"]] == [
        "representativeTranscriptOnly"
    ]
    assert "viewFilters" not in report.body["reportConfig"]


async def test_no_view_filters_sends_no_view_filters_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, report = _api(monkeypatch)

    await api.get_step_records(9, pagination=_PAGE)

    assert report.body == {"reportConfig": {"pagination": _PAGE}}
