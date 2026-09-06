"""The aiExpression reporter call: what it may send, and what it reads back.

The reporter generates a summary when the request asks for one, and generation
spends the deployment's whole daily budget. This client cannot ask.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.ai_expression import (
    AI_EXPRESSION_REPORT_PATH,
    AiExpressionReport,
    AiExpressionReportConfig,
    AiExpressionStatus,
)
from veupathdb.wdk.client import VEuPathDBClient

CACHED_GENE = "PF3D7_1133400"
UNCACHED_GENE = "PF3D7_0709000"


class _PostRecorder:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.paths: list[str] = []
        self.bodies: list[dict[str, Any]] = []

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> Any:
        self.paths.append(path)
        self.bodies.append(json or {})
        return self._response


def _client(
    monkeypatch: pytest.MonkeyPatch, response: Any
) -> tuple[VEuPathDBClient, _PostRecorder]:
    client = VEuPathDBClient("https://example.invalid/service")
    post = _PostRecorder(response)
    monkeypatch.setattr(client, "post", post)
    return client, post


class TestTheRequestCanNeverAskForGeneration:
    def test_the_report_config_serializes_generation_off(self) -> None:
        body = AiExpressionReportConfig().model_dump(by_alias=True)

        assert body == {"populateIfNotPresent": False}

    def test_a_config_that_asks_for_generation_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            AiExpressionReportConfig.model_validate({"populateIfNotPresent": True})

    async def test_the_sent_body_never_carries_a_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, post = _client(monkeypatch, {})

        await client.get_ai_expression_report(f"{CACHED_GENE},PlasmoDB")

        assert post.paths == [AI_EXPRESSION_REPORT_PATH]
        assert post.bodies[0]["reportConfig"] == {"populateIfNotPresent": False}
        assert post.bodies[0]["searchConfig"] == {
            "parameters": {"primaryKeys": f"{CACHED_GENE},PlasmoDB"}
        }


class TestTheRecordedResponsesParse:
    async def test_a_gene_with_every_experiment_cached_reports_its_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded = load_recorded("ai_expression_every_experiment_cached")
        client, _ = _client(monkeypatch, recorded.json_body())

        report = await client.get_ai_expression_report(f"{CACHED_GENE},PlasmoDB")
        gene = report.gene(CACHED_GENE)

        assert gene is not None
        assert gene.num_experiments == gene.num_experiments_complete
        assert gene.num_experiments > 0
        assert len(gene.experiment_status) == gene.num_experiments

    async def test_a_gene_with_nothing_cached_carries_no_summary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded = load_recorded("ai_expression_nothing_cached")
        client, _ = _client(monkeypatch, recorded.json_body())

        report = await client.get_ai_expression_report(f"{UNCACHED_GENE},PlasmoDB")
        gene = report.gene(UNCACHED_GENE)

        assert gene is not None
        assert gene.result_status is AiExpressionStatus.EXPERIMENTS_INCOMPLETE
        assert gene.expression_summary is None
        assert gene.num_experiments_complete == 0

    async def test_the_report_names_only_the_gene_that_was_asked_for(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded = load_recorded("ai_expression_nothing_cached")
        client, _ = _client(monkeypatch, recorded.json_body())

        report = await client.get_ai_expression_report(f"{UNCACHED_GENE},PlasmoDB")

        assert sorted(report.root) == [UNCACHED_GENE]


class TestAGeneratedSummaryReadsAsItsUpstreamTypeDeclaresIt:
    """The shape upstream's own client declares for a ``present`` result.

    ``aiExpressionTypes.ts`` and ``Summarizer.java``'s response schema name
    these keys. No live site answers ``present`` under the current model
    digest, so the shape is read from the source that defines it.
    """

    def test_the_summary_and_its_topics_parse(self) -> None:
        report = AiExpressionReport.model_validate(
            {
                CACHED_GENE: {
                    "resultStatus": "present",
                    "numExperiments": 2,
                    "numExperimentsComplete": 2,
                    "expressionSummary": {
                        "headline": "Peak expression in late schizonts",
                        "one_paragraph_summary": "<strong>Kelch13</strong> rises.",
                        "topics": [
                            {
                                "headline": "Asexual cycle",
                                "one_sentence_summary": "Rises at schizogony.",
                                "summaries": [
                                    {
                                        "one_sentence_summary": "Upregulated.",
                                        "notes": "Two replicates only.",
                                        "confidence": 4,
                                        "biological_importance": 5,
                                        "dataset_id": "DS_8ecf65d1b7",
                                        "experiment_keywords": ["schizont"],
                                        "embedding_vector": [0.1, 0.2],
                                    }
                                ],
                            }
                        ],
                    },
                }
            }
        )
        gene = report.gene(CACHED_GENE)

        assert gene is not None
        assert gene.result_status is AiExpressionStatus.PRESENT
        assert gene.expression_summary is not None
        assert gene.expression_summary.headline == "Peak expression in late schizonts"
        topic = gene.expression_summary.topics[0]
        assert topic.summaries[0].dataset_id == "DS_8ecf65d1b7"
        assert topic.summaries[0].experiment_keywords == ["schizont"]
