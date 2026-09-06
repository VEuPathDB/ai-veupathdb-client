"""The aiExpression reporter's request and response, as VEuPathDB's own client reads them.

The site computes the summary in Java and caches it. This client only reads.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from veupathdb.model import CamelModel

AI_EXPRESSION_RECORD_TYPE = "gene"
AI_EXPRESSION_SEARCH = "single_record_question_GeneRecordClasses_GeneRecordClass"
AI_EXPRESSION_REPORTER = "aiExpression"
AI_EXPRESSION_REPORT_PATH = (
    f"/record-types/{AI_EXPRESSION_RECORD_TYPE}/searches/"
    f"{AI_EXPRESSION_SEARCH}/reports/{AI_EXPRESSION_REPORTER}"
)


class AiExpressionStatus(StrEnum):
    """What the site holds for one cache entry."""

    PRESENT = "present"
    MISSING = "missing"
    FAILED = "failed"
    EXPIRED = "expired"
    CORRUPTED = "corrupted"
    UNDETERMINED = "undetermined"
    EXPERIMENTS_INCOMPLETE = "experiments_incomplete"


class AiExpressionReportConfig(CamelModel):
    """The reporter configuration this client sends.

    Generation is never requested. A request that asks for it spends the
    deployment's whole daily budget and makes the feature answer 503 for every
    site until midnight.
    """

    model_config = ConfigDict(frozen=True)

    populate_if_not_present: Literal[False] = False


class AiExperimentSummary(BaseModel):
    """One experiment's line. The keys are the summarizer's JSON schema."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    one_sentence_summary: str = ""
    notes: str = ""
    confidence: int = 0
    biological_importance: int = 0
    dataset_id: str = ""
    experiment_keywords: list[str] = Field(default_factory=list)


class AiExpressionTopic(BaseModel):
    """One group of experiments the summarizer named."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    headline: str = ""
    one_sentence_summary: str = ""
    summaries: list[AiExperimentSummary] = Field(default_factory=list)


class AiExpressionSummary(BaseModel):
    """The generated summary of one gene's expression."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    headline: str = ""
    one_paragraph_summary: str = ""
    topics: list[AiExpressionTopic] = Field(default_factory=list)


class AiExpressionGeneResponse(CamelModel):
    """What the site holds for one gene. The summary is absent unless generated."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    result_status: AiExpressionStatus
    num_experiments: int = 0
    num_experiments_complete: int = 0
    experiment_status: dict[str, AiExpressionStatus] = Field(default_factory=dict)
    expression_summary: AiExpressionSummary | None = None


class AiExpressionReport(RootModel[dict[str, AiExpressionGeneResponse]]):
    """The reporter's body: one entry per record, keyed by gene id."""

    def gene(self, gene_id: str) -> AiExpressionGeneResponse | None:
        """The entry for *gene_id*, or None when the report names no such gene."""
        return self.root.get(gene_id)
