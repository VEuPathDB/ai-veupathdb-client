"""A step's column counted by its word cloud reporter (WDK-ANS-011)."""

from __future__ import annotations

import pydantic
import pytest
from pydantic import JsonValue
from tests.unit.wdk._step_writes import Recorder

from veupathdb.errors import DataParsingError, VEuPathDBError, VEuPathDBErrorCode
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import ColumnNotCountableError
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import WDKWordCounts

_REPORTER = "abbreviation-wordCloud"
_CAP_SENTINEL: JsonValue = {"tags": [{"word": "Too many words", "count": 1}]}


def _api(
    monkeypatch: pytest.MonkeyPatch, reply: JsonValue
) -> tuple[StrategyAPI, Recorder]:
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    report = Recorder(reply=reply)
    monkeypatch.setattr(api.client, "post", report)
    return api, report


def _recorded_counts() -> JsonValue:
    return load_recorded("orthomcl_word_counts_by_abbreviation").json_body()


@pytest.mark.skipif(
    needs_qa_recording("wdk/orthomcl_word_counts_by_abbreviation.json"),
    reason=NEEDS_QA_RECORDING,
)
async def test_a_steps_word_counts_are_read_with_the_columns_reporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, report = _api(monkeypatch, _recorded_counts())

    counts = await api.get_step_word_counts(101, _REPORTER)

    assert report.paths == ["/users/1/steps/101/reports/abbreviation-wordCloud"]
    assert report.bodies == [{"reportConfig": {}}]
    assert (len(counts.tags), counts.total) == (139, 139)
    assert {tag.count for tag in counts.tags} == {1}


async def test_a_word_count_answer_without_tags_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, _ = _api(monkeypatch, {"histogram": []})

    with pytest.raises(DataParsingError, match=_REPORTER):
        await api.get_step_word_counts(101, _REPORTER)


async def test_the_cap_sentinel_is_refused_on_the_step_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, _ = _api(monkeypatch, _CAP_SENTINEL)

    with pytest.raises(
        DataParsingError,
        match=r"(?s)abbreviation-wordCloud report for step 101: .*10,000 distinct words",
    ):
        await api.get_step_word_counts(101, _REPORTER)


def test_the_cap_sentinel_is_not_a_count() -> None:
    with pytest.raises(pydantic.ValidationError, match="10,000 distinct words"):
        WDKWordCounts.model_validate(_CAP_SENTINEL)


def test_one_genuine_tag_is_a_count() -> None:
    counts = WDKWordCounts.model_validate({"tags": [{"word": "pfal", "count": 1}]})

    assert counts.total == 1


@pytest.mark.skipif(
    needs_qa_recording("wdk/orthomcl_word_counts_by_abbreviation.json"),
    reason=NEEDS_QA_RECORDING,
)
def test_counts_that_sum_to_the_step_are_read_per_value() -> None:
    counts = WDKWordCounts.model_validate(_recorded_counts())

    per_value = counts.record_counts(139)

    assert (len(per_value), per_value["pfal"], set(per_value.values())) == (
        139,
        1,
        {1},
    )


def test_counts_that_miss_the_step_are_refused() -> None:
    counts = WDKWordCounts.model_validate(
        {
            "tags": [
                {"count": 18260, "word": "bpli"},
                {"count": 9365, "word": "osat"},
            ]
        }
    )

    with pytest.raises(
        ColumnNotCountableError, match=r"sum to 27625.*holds 27626 records"
    ) as refused:
        counts.record_counts(27626)

    assert isinstance(refused.value, VEuPathDBError)
    assert not isinstance(refused.value, DataParsingError)
    assert refused.value.code is VEuPathDBErrorCode.VALIDATION_ERROR


@pytest.mark.skipif(
    needs_qa_recording("wdk/orthomcl_word_counts_by_taxon_name.json"),
    reason=NEEDS_QA_RECORDING,
)
def test_a_column_of_several_words_per_value_is_not_counted_per_record() -> None:
    counts = WDKWordCounts.model_validate(
        load_recorded("orthomcl_word_counts_by_taxon_name").json_body()
    )

    words = {tag.word: tag.count for tag in counts.tags}

    assert (len(counts.tags), counts.total) == (204, 460)
    assert (words["Plasmodium"], words["strain"]) == (61, 32)
    with pytest.raises(ColumnNotCountableError, match=r"sum to 460.*holds 139 records"):
        counts.record_counts(139)
