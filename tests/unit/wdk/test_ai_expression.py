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
    AiExpressionGeneResponse,
    AiExpressionReportConfig,
    AiExpressionStatus,
)
from veupathdb.wdk.client import VEuPathDBClient

SUMMARIZED_GENE = "PF3D7_0709000"
INCOMPLETE_GENE = "PF3D7_1133400"


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

        await client.get_ai_expression_report(f"{INCOMPLETE_GENE},PlasmoDB")

        assert post.paths == [AI_EXPRESSION_REPORT_PATH]
        assert post.bodies[0]["reportConfig"] == {"populateIfNotPresent": False}
        assert post.bodies[0]["searchConfig"] == {
            "parameters": {"primaryKeys": f"{INCOMPLETE_GENE},PlasmoDB"}
        }


class TestTheRecordedSummarizedGene:
    """The recorded ``present`` entry: a summary, no counts, one incompleteness flag."""

    async def _gene(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> AiExpressionGeneResponse | None:
        recorded = load_recorded("ai_expression_summary_present")
        client, _ = _client(monkeypatch, recorded.json_body())

        report = await client.get_ai_expression_report(f"{SUMMARIZED_GENE},PlasmoDB")
        return report.gene(SUMMARIZED_GENE)

    async def test_the_summary_and_its_topics_parse(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gene = await self._gene(monkeypatch)

        assert gene is not None
        assert gene.result_status is AiExpressionStatus.PRESENT
        summary = gene.expression_summary
        assert summary is not None
        assert summary.headline == (
            "Ring-stage-peaking transcript with recurrent stage-specific "
            "antisense activity"
        )
        assert [topic.headline for topic in summary.topics] == [
            "Consistent cyclical peak at ring/early trophozoite stage across the IDC",
            "Ring-stage bias extends across the broader parasite life cycle",
            "Stage-restricted antisense transcription hotspots",
            "Other",
        ]
        first = summary.topics[0]
        assert len(first.summaries) == 10
        assert first.summaries[0].dataset_id == "DS_ee861a9187"
        assert first.summaries[0].confidence == 4
        assert first.summaries[0].biological_importance == 4
        assert first.summaries[0].experiment_keywords == [
            "RNA-Seq",
            "intraerythrocytic development cycle",
            "time-series",
            "strand-specific",
            "Plasmodium falciparum",
            "sense/antisense transcription",
        ]

    async def test_every_summary_line_names_its_experiment_and_assay(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gene = await self._gene(monkeypatch)

        assert gene is not None
        summary = gene.expression_summary
        assert summary is not None
        lines = [line for topic in summary.topics for line in topic.summaries]
        assert len(lines) == 41
        assert lines[0].experiment_name == (
            "Intraerythrocytic development cycle transcriptome (2018)"
        )
        assert lines[0].assay_type == "RNA-Seq"
        assert lines[2].experiment_name == "Pfal3D7 real-time transcription and decay"
        assert lines[2].assay_type == "array"
        assert {line.assay_type for line in lines} == {"RNA-Seq", "array"}
        assert len({line.experiment_name for line in lines}) == 41

    async def test_the_absent_counts_read_none_and_not_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gene = await self._gene(monkeypatch)

        assert gene is not None
        assert gene.num_experiments is None
        assert gene.num_experiments_complete is None
        assert gene.experiment_status == {}

    async def test_it_states_that_the_summary_covers_every_experiment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gene = await self._gene(monkeypatch)

        assert gene is not None
        assert gene.based_on_incomplete_data is False

    async def test_the_report_names_only_the_gene_that_was_asked_for(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded = load_recorded("ai_expression_summary_present")
        client, _ = _client(monkeypatch, recorded.json_body())

        report = await client.get_ai_expression_report(f"{SUMMARIZED_GENE},PlasmoDB")

        assert sorted(report.root) == [SUMMARIZED_GENE]


class TestTheRecordedGeneWithExperimentsOutstanding:
    """The recorded ``experiments_incomplete`` entry: counts, statuses, no summary."""

    async def _gene(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> AiExpressionGeneResponse | None:
        recorded = load_recorded("ai_expression_experiments_incomplete")
        client, _ = _client(monkeypatch, recorded.json_body())

        report = await client.get_ai_expression_report(f"{INCOMPLETE_GENE},PlasmoDB")
        return report.gene(INCOMPLETE_GENE)

    async def test_it_carries_the_counts_and_no_summary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gene = await self._gene(monkeypatch)

        assert gene is not None
        assert gene.result_status is AiExpressionStatus.EXPERIMENTS_INCOMPLETE
        assert gene.expression_summary is None
        assert gene.num_experiments == 41
        assert gene.num_experiments_complete == 0

    async def test_every_experiment_of_it_reads_expired(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gene = await self._gene(monkeypatch)

        assert gene is not None
        assert len(gene.experiment_status) == 41
        assert set(gene.experiment_status.values()) == {AiExpressionStatus.EXPIRED}

    async def test_an_entry_that_omits_the_flag_reads_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gene = await self._gene(monkeypatch)

        assert gene is not None
        assert gene.based_on_incomplete_data is None
