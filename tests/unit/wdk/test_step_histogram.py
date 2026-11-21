from __future__ import annotations

import pydantic
import pytest
from pydantic import JsonValue
from tests.unit.wdk._step_writes import Recorder

from veupathdb.errors import DataParsingError
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKAttributeHistogram, WDKFilterValue
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI

_ONE_PER_GENE = WDKFilterValue(name="representativeTranscriptOnly", value={})


def _api(
    monkeypatch: pytest.MonkeyPatch, reply: JsonValue
) -> tuple[StrategyAPI, Recorder]:
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    report = Recorder(reply=reply)
    monkeypatch.setattr(api.client, "post", report)
    return api, report


def _recorded() -> JsonValue:
    return load_recorded("weight_histogram_by_molecular_weight").json_body()


@pytest.mark.skipif(
    needs_qa_recording("wdk/weight_histogram_by_molecular_weight.json"),
    reason=NEEDS_QA_RECORDING,
)
async def test_wdk_ans_012_a_steps_weights_are_counted_by_the_columns_histogram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, report = _api(monkeypatch, _recorded())

    histogram = await api.get_step_histogram(
        101, "wdk_weight", view_filters=[_ONE_PER_GENE]
    )

    assert report.paths == ["/users/1/steps/101/reports/wdk_weight-histogram"]
    assert report.bodies == [
        {
            "reportConfig": {},
            "viewFilters": [
                {"name": "representativeTranscriptOnly", "value": {}, "disabled": False}
            ],
        }
    ]
    assert (histogram.type, list(histogram.data), histogram.attr_label) == (
        "int",
        ["5"],
        "Search Weight",
    )


async def test_a_histogram_without_its_view_filters_sends_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, report = _api(
        monkeypatch,
        {
            "data": {"1": 2043, "2": 1062},
            "type": "int",
            "attrLabel": "Search Weight",
            "recordCountLabel": "# of Genes",
        },
    )

    histogram = await api.get_step_histogram(101, "wdk_weight")

    assert (report.bodies, histogram.data) == (
        [{"reportConfig": {}}],
        {"1": 2043, "2": 1062},
    )


async def test_a_histogram_answer_without_data_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, _ = _api(monkeypatch, {"tags": []})

    with pytest.raises(DataParsingError, match="wdk_weight-histogram"):
        await api.get_step_histogram(101, "wdk_weight")


def test_a_histogram_of_an_unknown_type_is_refused() -> None:
    with pytest.raises(pydantic.ValidationError, match="type"):
        WDKAttributeHistogram.model_validate(
            {
                "data": {},
                "type": "date",
                "attrLabel": "Search Weight",
                "recordCountLabel": "# of Genes",
            }
        )
