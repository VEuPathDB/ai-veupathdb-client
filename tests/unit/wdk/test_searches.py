"""What the dependent-vocabulary refresh takes, and how it refuses.

``ParamValueSetRequest.parse`` reads ``contextParamValues`` with
``getJSONObject`` and ``changedParam.value`` with ``getString``. A failure of
either is a 400. Only the 422s are about the values.
"""

from __future__ import annotations

from typing import Any

import pytest

from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk._failures import validation_bundle
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.wdk_models import WDKSearchConfig

_REFRESH_PATH = (
    "/record-types/transcript/searches/GenesByLocation/refreshed-dependent-params"
)


class _BodyRecorder:
    def __init__(self, response: Any = None) -> None:
        self._response = [] if response is None else response
        self.bodies: list[dict[str, Any]] = []
        self.paths: list[str] = []

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> Any:
        self.paths.append(path)
        self.bodies.append(json or {})
        return self._response


def _client(
    monkeypatch: pytest.MonkeyPatch, response: Any = None
) -> tuple[VEuPathDBClient, _BodyRecorder]:
    client = VEuPathDBClient("https://example.invalid/service")
    post = _BodyRecorder(response)
    monkeypatch.setattr(client, "post", post)
    return client, post


class TestWdkVocab006TheRequestShapeEarnsNo400:
    async def test_wdk_vocab_006_the_changed_param_is_always_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, post = _client(monkeypatch)

        await client.get_refreshed_dependent_params(
            "transcript", "GenesByLocation", "organismSinglePick", {}
        )

        assert post.paths == [_REFRESH_PATH]
        assert "changedParam" in post.bodies[0]

    async def test_wdk_vocab_006_the_changed_value_is_a_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, post = _client(monkeypatch)

        await client.get_refreshed_dependent_params(
            "transcript",
            "GenesByLocation",
            "organismSinglePick",
            {"organismSinglePick": '["Plasmodium falciparum 3D7"]'},
        )

        assert post.bodies[0]["changedParam"] == {
            "name": "organismSinglePick",
            "value": '["Plasmodium falciparum 3D7"]',
        }
        assert isinstance(post.bodies[0]["changedParam"]["value"], str)

    async def test_wdk_vocab_006_the_context_is_an_object(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, post = _client(monkeypatch)

        await client.get_refreshed_dependent_params(
            "transcript", "GenesByLocation", "organismSinglePick", {"a": "1"}
        )

        assert post.bodies[0]["contextParamValues"] == {"a": "1"}


class TestWdkVocab006TheRefusalsSplitAt400And422:
    def test_wdk_vocab_006_a_missing_changed_param_is_a_400(self) -> None:
        recorded = load_recorded("refresh_without_changed_param")

        assert recorded.provenance.status == 400
        assert "'changedParam' property is required" in recorded.raw_text()

    def test_wdk_vocab_006_a_non_string_value_is_a_400(self) -> None:
        recorded = load_recorded("refresh_with_a_non_string_value")

        assert recorded.provenance.status == 400
        assert 'JSONObject["value"] is not a string' in recorded.raw_text()

    def test_wdk_vocab_006_a_value_outside_the_vocabulary_is_a_422(self) -> None:
        recorded = load_recorded("refresh_with_a_value_outside_the_vocabulary")

        assert recorded.provenance.status == 422
        bundle = validation_bundle(recorded.raw_text())
        assert bundle is not None
        assert "is invalid" in " ".join(bundle.messages())

    def test_wdk_vocab_006_an_unknown_parameter_is_a_422(self) -> None:
        recorded = load_recorded("refresh_with_an_unknown_parameter")

        assert recorded.provenance.status == 422

    def test_wdk_vocab_006_the_refusal_names_the_query_full_name(self) -> None:
        # A third naming vocabulary: neither the url segment nor the full name.
        recorded = load_recorded("refresh_with_an_unknown_parameter")
        bundle = validation_bundle(recorded.raw_text())

        assert bundle is not None
        assert "GeneId.GenesByLocation" in " ".join(bundle.messages())

    def test_wdk_vocab_006_only_the_400s_are_about_our_serialization(self) -> None:
        prose = load_recorded("refresh_without_changed_param")
        verdict = load_recorded("refresh_with_a_value_outside_the_vocabulary")

        assert validation_bundle(prose.raw_text()) is None
        rejected = validation_bundle(verdict.raw_text())
        assert rejected is not None
        assert "is invalid" in " ".join(rejected.messages())


async def test_wdk_step_005_an_unpersisted_count_uses_the_search_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The equivalent of a step count with no step and no strategy at all."""
    client, post = _client(
        monkeypatch, {"meta": {"totalCount": 105, "responseCount": 0}, "records": []}
    )

    answer = await client.run_search_report(
        "transcript", "GenesByMolecularWeight", WDKSearchConfig()
    )

    assert answer.meta.records_returned() == 105
    assert post.paths == [
        "/record-types/transcript/searches/GenesByMolecularWeight/reports/standard"
    ]
