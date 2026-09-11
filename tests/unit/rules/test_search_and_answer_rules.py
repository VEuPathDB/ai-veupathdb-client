"""The search and answer rules, over the recorded refusals and the report body."""

from __future__ import annotations

from typing import Any

import pytest

from veupathdb.json_types import JSONObject
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk._failures import wdk_failure
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import WDKSearch, WDKWordEnrichmentRow


class _Report:
    """Answers one recorded answer body and keeps every request it was sent."""

    def __init__(self, body: Any) -> None:
        self._body = body
        self.paths: list[str] = []
        self.bodies: list[dict[str, Any]] = []

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> Any:
        self.paths.append(path)
        self.bodies.append(json or {})
        return self._body


def _api(monkeypatch: pytest.MonkeyPatch) -> tuple[StrategyAPI, _Report]:
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    report = _Report(load_recorded("answer_report_by_molecular_weight").json_body())
    monkeypatch.setattr(api.client, "post", report)
    return api, report


def _search_body() -> JSONObject:
    body = load_recorded("search_genes_by_molecular_weight").json_body()
    assert isinstance(body, dict)
    search = body["searchData"]
    assert isinstance(search, dict)
    return search


async def test_wdk_ans_001_a_step_report_body_carries_only_the_report_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The step endpoint owns the search config already, so the body omits it."""
    api, report = _api(monkeypatch)

    await api.get_step_records(9, attributes=["primary_key"])

    assert list(report.bodies[0]) == ["reportConfig"]


async def test_wdk_ans_002_no_attributes_asked_for_sends_no_attributes_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty `attributes` returns every record with no attributes, so it is omitted."""
    api, report = _api(monkeypatch)

    await api.get_step_records(9)

    assert "attributes" not in report.bodies[0]["reportConfig"]


async def test_wdk_ans_003_a_count_asks_for_zero_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`numRecords: 0` returns the meta and no records."""
    api, report = _api(monkeypatch)

    await api.get_step_count(9)

    assert report.bodies[0]["reportConfig"]["pagination"] == {
        "offset": 0,
        "numRecords": 0,
    }


async def test_wdk_ans_005_a_paged_read_goes_through_the_standard_reporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the standard reporter honours pagination and sorting."""
    api, report = _api(monkeypatch)

    await api.get_step_records(9, pagination={"offset": 0, "numRecords": 10})

    assert report.paths[0].endswith("/reports/standard")


def test_wdk_ans_007_the_word_plugin_serves_its_description_as_pathway_name() -> None:
    """The word row carries no `descrip`; the description arrives as `pathwayName`."""
    row = WDKWordEnrichmentRow.model_validate(
        {"word": "kinase", "pathwayName": "protein kinase activity"}
    )

    assert row.word == "kinase"
    assert row.pathway_name == "protein kinase activity"


def test_wdk_search_001_the_wrong_record_type_is_a_404_naming_the_record_class() -> (
    None
):
    """A search belongs to one record class, and the refusal says which."""
    recorded = load_recorded("search_under_the_wrong_record_type")
    refusal = wdk_failure(
        "GET",
        "/record-types/organism/searches/GenesByMolecularWeight",
        recorded.provenance.status,
        recorded.raw_text(),
    )

    assert recorded.provenance.status == 404
    assert "OrganismRecordClass" in str(refusal)


def test_wdk_search_002_the_full_name_is_not_an_address_and_the_url_segment_is() -> (
    None
):
    """A search is addressed by `urlSegment`; its two-part `fullName` is a 404."""
    recorded = load_recorded("search_by_full_name")
    search = WDKSearch.model_validate(_search_body())

    assert recorded.provenance.status == 404
    assert search.full_name == "GeneQuestions.GenesByMolecularWeight"
    assert search.url_segment == "GenesByMolecularWeight"
    assert recorded.provenance.url.endswith(f"/searches/{search.full_name}")


def test_wdk_search_004_the_parameter_list_is_param_names_and_a_group_is_presentation() -> (
    None
):
    """Every group entry names a parameter the search already lists."""
    search = WDKSearch.model_validate(_search_body())
    grouped = {name for group in search.groups for name in group.parameters}

    assert search.param_names == [
        "organism",
        "min_molecular_weight",
        "max_molecular_weight",
    ]
    assert grouped <= set(search.param_names)
    assert [param.name for param in search.parameters or []] == search.param_names
