"""The validation rules, over the analysis endpoints this client reads."""

from __future__ import annotations

from typing import Any

import pytest

from veupathdb.json_types import JSONObject
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.analysis_result import WDKAnalysisNotReadyError
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.analyses import AnalysisPollConfig
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import WDKStepAnalysisTypeResponse

_FORM: dict[str, Any] = {
    "searchData": {
        "name": "go-enrichment",
        "displayName": "GO Enrichment",
        "paramNames": ["goAssociationsSources", "pValueCutoff"],
        "parameters": [
            {
                "name": "pValueCutoff",
                "type": "string",
                "displayName": "P-value cutoff",
                "initialDisplayValue": "0.05",
            }
        ],
    },
    "validation": {"level": "DISPLAYABLE", "isValid": True},
}


class _Answer:
    """Answers one body and keeps every request it was sent."""

    def __init__(self, body: Any) -> None:
        self._body = body
        self.bodies: list[JSONObject] = []

    async def __call__(
        self, path: str, json: JSONObject | None = None, **_: object
    ) -> Any:
        del path
        self.bodies.append(json or {})
        return self._body


def test_wdk_valid_007_a_displayable_bundle_parses() -> None:
    """`DISPLAYABLE` is a sixth level, and a level is not an enum here."""
    response = WDKStepAnalysisTypeResponse.model_validate(_FORM)

    assert response.validation.level == "DISPLAYABLE"
    assert response.search_data.name == "go-enrichment"


async def test_wdk_valid_008_an_empty_result_body_is_not_a_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 204 carries no body, which is not an empty result."""
    client = VEuPathDBClient("https://example.invalid/service")
    monkeypatch.setattr(client, "get", _Answer(None))

    with pytest.raises(WDKAnalysisNotReadyError):
        await client.get_analysis_result("1", 9, 3)


async def test_wdk_valid_010_the_listing_carries_two_fields_per_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The listing is an id and a display name, never the instance."""
    client = VEuPathDBClient("https://example.invalid/service")
    monkeypatch.setattr(
        client,
        "get",
        _Answer([{"analysisId": 3, "displayName": "GO Enrichment"}]),
    )

    listed = await client.list_step_analyses("1", 9)

    assert [(entry.analysis_id, entry.display_name) for entry in listed] == [
        (3, "GO Enrichment")
    ]


class _Run:
    """Answers each call of one analysis run and keeps the creation body."""

    def __init__(self) -> None:
        self.created: list[JSONObject] = []

    async def post(self, path: str, json: JSONObject | None = None, **_: object) -> Any:
        if path.endswith("/reports/standard"):
            return load_recorded("answer_report_by_molecular_weight").json_body()
        if path.endswith("/analyses"):
            self.created.append(json or {})
            return {
                "analysisId": 3,
                "stepId": 9,
                "analysisName": "go-enrichment",
                "displayName": "GO Enrichment",
            }
        return None

    async def get(self, path: str, **_: object) -> Any:
        if path.endswith("/result/status"):
            return {"status": "COMPLETE"}
        return {"resultData": []}


async def test_wdk_valid_011_a_form_default_is_not_applied_by_the_creation_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The form hands a default; the create sends what the caller stated and no more."""
    api = StrategyAPI(VEuPathDBClient("https://example.invalid/service"), "1")
    run = _Run()
    monkeypatch.setattr(api.client, "post", run.post)
    monkeypatch.setattr(api.client, "get", run.get)
    form = WDKStepAnalysisTypeResponse.model_validate(_FORM)

    await api.run_step_analysis(
        9,
        "go-enrichment",
        poll_config=AnalysisPollConfig(poll_interval=0.0),
        user_id="1",
    )

    declared = form.search_data.parameters or []
    assert [param.initial_display_value for param in declared] == ["0.05"]
    assert run.created[0]["parameters"] == {}
