"""A search report sends a countOnlyLeaves tree value as its leaves, as a step does."""

from __future__ import annotations

import json
from typing import Any

import pytest
from tests.unit.wdk._step_writes import Recorder

from veupathdb.json_types import JSONObject
from veupathdb.testing import NEEDS_QA_RECORDING
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.wdk_models import NewStepSpec, WDKSearchConfig

pytestmark = pytest.mark.skip(reason=NEEDS_QA_RECORDING)

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


def _organism(body: dict[str, Any]) -> list[str]:
    return list(json.loads(body["searchConfig"]["parameters"]["organism"]))


async def test_a_parent_organism_is_sent_as_the_leaves_under_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sent = _client(monkeypatch)

    await client.run_search_report("transcript", _SEARCH, _CONFIG, _PAGE)

    organisms = _organism(sent.body)
    assert len(organisms) == 61
    assert organisms[:2] == ["Plasmodium adleri G01", "Plasmodium berghei ANKA"]
    assert "Plasmodium" not in organisms
    assert sent.body["searchConfig"]["parameters"]["min_molecular_weight"] == "10000"


async def test_a_report_and_a_step_send_the_same_organisms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sent = _client(monkeypatch)
    await client.run_search_report("transcript", _SEARCH, _CONFIG, _PAGE)
    report_organisms = _organism(sent.body)

    sent.reply = {"id": 7}
    await StrategyAPI(client, "1").create_step(
        NewStepSpec(search_name=_SEARCH, search_config=_CONFIG), "transcript"
    )

    assert _organism(sent.body) == report_organisms


async def test_a_report_with_no_parameters_reads_no_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sent = _client(monkeypatch)
    catalog = _Catalog()
    monkeypatch.setattr(client, "get", catalog)

    await client.run_search_report("organism", "GenomeDataTypes", WDKSearchConfig())

    assert catalog.paths == []
    assert sent.body["searchConfig"] == {"parameters": {}}


async def test_a_report_with_no_term_list_reads_no_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a multi-pick value names a tree parent, and WDK sends it as a list."""
    client, sent = _client(monkeypatch)
    catalog = _Catalog()
    monkeypatch.setattr(client, "get", catalog)
    by_id = WDKSearchConfig(parameters={"ds_gene_ids": "12345", "weight": "10"})

    await client.run_search_report("transcript", "GeneByLocusTag", by_id, _PAGE)

    assert catalog.paths == []
    assert sent.body["searchConfig"]["parameters"] == {
        "ds_gene_ids": "12345",
        "weight": "10",
    }
