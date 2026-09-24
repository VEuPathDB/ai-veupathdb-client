"""A search report carries its view filters beside the report config (WDK-FILTER-003)."""

from __future__ import annotations

import pytest
from tests.unit.wdk._step_writes import Recorder

from veupathdb.devtools.fixtures import verify_body
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.wdk_models import WDKFilterValue, WDKSearchConfig

_ONE_PER_GENE = WDKFilterValue(name="representativeTranscriptOnly", value={})
_CONFIG = WDKSearchConfig(parameters={"organism": '["Plasmodium falciparum 3D7"]'})
_PAGE = {"pagination": {"offset": 0, "numRecords": 10}}


def _client(monkeypatch: pytest.MonkeyPatch) -> tuple[VEuPathDBClient, Recorder]:
    client = VEuPathDBClient("https://example.invalid/service")
    report = Recorder(
        reply=load_recorded("answer_report_by_molecular_weight").json_body()
    )
    monkeypatch.setattr(client, "post", report)
    return client, report


async def test_the_view_filters_sit_beside_the_search_and_report_configs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, report = _client(monkeypatch)

    await client.run_search_report(
        "transcript",
        "GenesByMolecularWeight",
        _CONFIG,
        _PAGE,
        view_filters=[_ONE_PER_GENE],
    )

    assert report.body == {
        "searchConfig": {"parameters": {"organism": '["Plasmodium falciparum 3D7"]'}},
        "reportConfig": _PAGE,
        "viewFilters": [
            {"name": "representativeTranscriptOnly", "value": {}, "disabled": False}
        ],
    }
    assert verify_body("wdk.answer.post-request", report.body) == ()


async def test_no_view_filters_sends_no_view_filters_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, report = _client(monkeypatch)

    await client.run_search_report(
        "transcript", "GenesByMolecularWeight", _CONFIG, _PAGE
    )

    assert report.body == {
        "searchConfig": {"parameters": {"organism": '["Plasmodium falciparum 3D7"]'}},
        "reportConfig": _PAGE,
    }
