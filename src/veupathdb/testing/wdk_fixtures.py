"""The pinned WDK responses the hermetic lane reads, and where they came from."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from veupathdb.json_types import JSONObject
from veupathdb.testing.fixture_store import FIXTURE_ROOT
from veupathdb.wdk.ai_expression import AI_EXPRESSION_REPORT_PATH

FIXTURE_DIR = FIXTURE_ROOT / "wdk"
SCHEMA_DIR = FIXTURE_DIR / "schema"
SCHEMA_PIN_FILE = FIXTURE_DIR / "schema-pin.json"

_TRANSCRIPT = "/record-types/transcript/searches"
_BOOLEAN_TRANSCRIPT = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


class FixtureRequest(BaseModel):
    """One recorded exchange: what to ask, where, and which rules read it.

    ``in_schema`` and ``out_schema`` carry the ``@InSchema`` and ``@OutSchema``
    values WDK binds to the endpoint, and only when the live service holds to
    them. Both are the dotted form the annotation uses.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    path: str
    reads: str
    site: str = "plasmodb"
    method: Literal["GET", "POST"] = "GET"
    params: dict[str, str] = Field(default_factory=dict)
    body: JSONObject | None = None
    in_schema: str | None = None
    out_schema: str | None = None

    @model_validator(mode="after")
    def _an_in_schema_needs_a_body(self) -> FixtureRequest:
        if self.in_schema is not None and self.body is None:
            msg = (
                f"{self.name}: an in_schema describes a request body, and there is none"
            )
            raise ValueError(msg)
        return self

    @property
    def file(self) -> Path:
        return FIXTURE_DIR / f"{self.name}.json"


class FixtureProvenance(BaseModel):
    """Where a recorded response came from, and when."""

    model_config = ConfigDict(frozen=True)

    site: str
    method: str
    url: str
    status: int
    content_type: str
    recorded_at: str
    reads: str


class RecordedWDKResponse(BaseModel):
    """A response as the wire carried it, plus where it came from.

    A body that parses as JSON is stored as JSON; a prose body is stored as
    text. Exactly one of the two is present.
    """

    model_config = ConfigDict(frozen=True)

    provenance: FixtureProvenance
    body: JsonValue = None
    text: str | None = None

    @model_validator(mode="after")
    def _one_body_form(self) -> RecordedWDKResponse:
        if (self.body is None) == (self.text is None):
            msg = (
                f"{self.provenance.url}: a fixture holds a JSON body or prose, not both"
            )
            raise ValueError(msg)
        return self

    def json_body(self) -> JsonValue:
        """The parsed body. A prose fixture raises rather than answer with None."""
        if self.body is None:
            msg = f"{self.provenance.url} recorded prose, not JSON"
            raise TypeError(msg)
        return self.body

    def raw_text(self) -> str:
        """The body as a string, whichever form it was stored in.

        A JSON body is re-serialized, so the characters are the content and
        not the whitespace the server chose.
        """
        return json.dumps(self.body) if self.text is None else self.text


FIXTURES: tuple[FixtureRequest, ...] = (
    FixtureRequest(
        name="record_types",
        path="/record-types",
        out_schema="wdk.records.get",
        reads="WDK-HTTP-004",
    ),
    FixtureRequest(
        name="record_type_build",
        path="/record-types/build",
        out_schema="wdk.records.name.get",
        reads="WDK-HTTP-004",
    ),
    FixtureRequest(
        name="answer_report_by_molecular_weight",
        path=f"{_TRANSCRIPT}/GenesByMolecularWeight/reports/standard",
        method="POST",
        body={
            "searchConfig": {
                "parameters": {
                    "min_molecular_weight": "50000",
                    "max_molecular_weight": "50100",
                    "organism": '["Plasmodium falciparum 3D7"]',
                }
            },
            "reportConfig": {
                "attributes": ["primary_key"],
                "tables": [],
                "pagination": {"offset": 0, "numRecords": 2},
            },
        },
        in_schema="wdk.answer.post-request",
        reads="WDK-HTTP-004",
    ),
    FixtureRequest(
        name="ai_expression_experiments_incomplete",
        path=AI_EXPRESSION_REPORT_PATH,
        method="POST",
        body={
            "searchConfig": {"parameters": {"primaryKeys": "PF3D7_1133400,PlasmoDB"}},
            "reportConfig": {"populateIfNotPresent": False},
        },
        reads="WDK-ANS-009",
    ),
    FixtureRequest(
        name="ai_expression_summary_present",
        path=AI_EXPRESSION_REPORT_PATH,
        method="POST",
        body={
            "searchConfig": {"parameters": {"primaryKeys": "PF3D7_0709000,PlasmoDB"}},
            "reportConfig": {"populateIfNotPresent": False},
        },
        reads="WDK-ANS-009",
    ),
    FixtureRequest(
        name="search_genes_by_molecular_weight",
        path=f"{_TRANSCRIPT}/GenesByMolecularWeight",
        params={"expandParams": "true"},
        reads="WDK-SEARCH-002, WDK-SEARCH-004, WDK-PARAM-002",
    ),
    FixtureRequest(
        name="search_boolean_transcript",
        path=f"{_TRANSCRIPT}/{_BOOLEAN_TRANSCRIPT}",
        params={"expandParams": "true"},
        reads="WDK-STEP-006, WDK-STEP-008",
    ),
    FixtureRequest(
        name="search_genes_by_orthologs",
        path=f"{_TRANSCRIPT}/GenesByOrthologs",
        params={"expandParams": "true"},
        reads="WDK-STEP-001",
    ),
    FixtureRequest(
        name="search_genes_by_location",
        path=f"{_TRANSCRIPT}/GenesByLocation",
        params={"expandParams": "true"},
        reads="WDK-PARAM-001, WDK-VOCAB-003, WDK-SEARCH-004",
    ),
    FixtureRequest(
        name="search_with_a_hidden_required_parameter",
        path=f"{_TRANSCRIPT}/GenesByPhenotypeEdaSubset_PlasmoDB_Rod_Mal_Phenotype_RSRC",
        params={"expandParams": "true"},
        reads="WDK-PARAM-011",
    ),
    FixtureRequest(
        name="search_genes_by_exon_count",
        path=f"{_TRANSCRIPT}/GenesByExonCount",
        params={"expandParams": "true"},
        reads="WDK-PARAM-003",
    ),
    FixtureRequest(
        name="search_under_the_wrong_record_type",
        path="/record-types/organism/searches/GenesByMolecularWeight",
        reads="WDK-SEARCH-001",
    ),
    FixtureRequest(
        name="search_by_full_name",
        path=f"{_TRANSCRIPT}/GeneQuestions.GenesByMolecularWeight",
        reads="WDK-SEARCH-002",
    ),
    FixtureRequest(
        name="refresh_without_changed_param",
        path=f"{_TRANSCRIPT}/GenesByLocation/refreshed-dependent-params",
        method="POST",
        body={"contextParamValues": {}},
        reads="WDK-VOCAB-006",
    ),
    FixtureRequest(
        name="refresh_with_a_non_string_value",
        path=f"{_TRANSCRIPT}/GenesByLocation/refreshed-dependent-params",
        method="POST",
        body={
            "changedParam": {"name": "organismSinglePick", "value": ["Nope"]},
            "contextParamValues": {"organismSinglePick": "Nope"},
        },
        reads="WDK-PARAM-002, WDK-VOCAB-006",
    ),
    FixtureRequest(
        name="refresh_with_a_value_outside_the_vocabulary",
        path=f"{_TRANSCRIPT}/GenesByLocation/refreshed-dependent-params",
        method="POST",
        body={
            "changedParam": {"name": "organismSinglePick", "value": "Nope"},
            "contextParamValues": {"organismSinglePick": "Nope"},
        },
        reads="WDK-VOCAB-006, WDK-VALID-001, WDK-VALID-006, WDK-HTTP-002",
    ),
    FixtureRequest(
        name="refresh_with_an_unknown_parameter",
        path=f"{_TRANSCRIPT}/GenesByLocation/refreshed-dependent-params",
        method="POST",
        body={
            "changedParam": {"name": "nope", "value": "x"},
            "contextParamValues": {"nope": "x"},
        },
        reads="WDK-VOCAB-006",
    ),
)

_BY_NAME = {fixture.name: fixture for fixture in FIXTURES}


def fixture_request(name: str) -> FixtureRequest:
    """The manifest entry of *name*, or a failure naming the store."""
    if name not in _BY_NAME:
        known = ", ".join(sorted(_BY_NAME))
        msg = f"no WDK fixture named {name!r}; the manifest holds: {known}"
        raise KeyError(msg)
    return _BY_NAME[name]


def load_recorded(name: str) -> RecordedWDKResponse:
    """Read one pinned response, or fail naming the command that records it."""
    path = fixture_request(name).file
    if not path.exists():
        msg = (
            f"{path} is missing; record it with "
            f"`python -m veupathdb.devtools.fixtures record --only {name}`"
        )
        raise FileNotFoundError(msg)
    return RecordedWDKResponse.model_validate_json(path.read_text())


__all__ = [
    "FIXTURES",
    "FIXTURE_DIR",
    "SCHEMA_DIR",
    "SCHEMA_PIN_FILE",
    "FixtureProvenance",
    "FixtureRequest",
    "RecordedWDKResponse",
    "fixture_request",
    "load_recorded",
]
