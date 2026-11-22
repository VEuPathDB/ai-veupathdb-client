"""A search report sends its parameters as given, as a step does."""

from __future__ import annotations

from typing import Any

import pytest
from tests.unit.wdk._step_writes import Recorder

from veupathdb.json_types import JSONObject
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import NewStepSpec, WDKSearchConfig

pytestmark = pytest.mark.skipif(
    needs_qa_recording(
        "wdk/answer_report_by_molecular_weight.json",
        "wdk/search_genes_by_molecular_weight.json",
    ),
    reason=NEEDS_QA_RECORDING,
)

_SEARCH = "GenesByMolecularWeight"
_PAGE: JSONObject = {"pagination": {"offset": 0, "numRecords": 0}}
_CONFIG = WDKSearchConfig(
    parameters={
        "organism": '["Plasmodium"]',
        "min_molecular_weight": "10000",
        "max_molecular_weight": "20000",
    }
)


class _Catalog:
    """Answers every GET with the recorded GenesByMolecularWeight search."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        self._body = load_recorded("search_genes_by_molecular_weight").json_body()

    async def __call__(self, path: str, **_: object) -> Any:
        self.paths.append(path)
        return self._body


def _client(monkeypatch: pytest.MonkeyPatch) -> tuple[VEuPathDBClient, Recorder]:
    client = VEuPathDBClient("https://example.invalid/service")
    sent = Recorder(
        reply=load_recorded("answer_report_by_molecular_weight").json_body()
    )
    monkeypatch.setattr(client, "get", _Catalog())
    monkeypatch.setattr(client, "post", sent)
    return client, sent


async def test_a_report_sends_a_parent_organism_as_given_and_reads_no_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sent = _client(monkeypatch)
    catalog = _Catalog()
    monkeypatch.setattr(client, "get", catalog)

    await client.run_search_report("transcript", _SEARCH, _CONFIG, _PAGE)

    assert catalog.paths == []
    assert sent.body["searchConfig"]["parameters"] == _CONFIG.parameters


async def test_a_step_sends_the_organisms_as_stated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sent = _client(monkeypatch)
    sent.reply = {"id": 7}

    await StrategyAPI(client, "1").create_step(
        NewStepSpec(search_name=_SEARCH, search_config=_CONFIG), "transcript"
    )

    assert sent.body["searchConfig"]["parameters"] == _CONFIG.parameters
