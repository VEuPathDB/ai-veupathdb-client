"""The sweep behind the hidden-required-default check, and its resumable report.

The sweep binds every required parameter of a search from that parameter's own
``initialDisplayValue`` and reads the count WDK answers.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx
import pydantic
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from veupathdb.model import CamelModel
from veupathdb.wdk.factory import get_wdk_client
from veupathdb.wdk.probe import WDKProbe

SITE = "plasmodb"
TRANSCRIPT = "/record-types/transcript/searches"
LIMIT_ENV = "WDK_HIDDEN_DEFAULTS_LIMIT"
_REPORT_ENV = "WDK_HIDDEN_DEFAULTS_REPORT"
_DEFAULT_REPORT = Path("wdk-hidden-defaults.json")
_CONCURRENCY = 6
_NOTE_CHARS = 600


class HiddenParam(BaseModel):
    """One required parameter and the value WDK publishes for it."""

    model_config = ConfigDict(frozen=True)

    name: str
    param_type: str
    default: str
    visible: bool


class SearchMeasurement(BaseModel):
    """What one search answered when every published default was bound.

    ``unmeasurable`` marks a search with a required parameter that has no
    default to bind, so nothing can be run without choosing a value.
    """

    search: str
    hidden: list[HiddenParam]
    bound: dict[str, str] = Field(default_factory=dict)
    unmeasurable: list[str] = Field(default_factory=list)
    status: int = 0
    total_count: int | None = None
    note: str = ""

    @property
    def returned_nothing(self) -> bool:
        return self.status == 200 and self.total_count == 0


class SweepReport(BaseModel):
    """Every search measured so far, so a later run resumes rather than repeats."""

    site: str
    measured: dict[str, SearchMeasurement] = Field(default_factory=dict)


class MetadataSweep(BaseModel):
    """Which searches carry a hidden required default, and which did not answer."""

    hidden: dict[str, list[HiddenParam]] = Field(default_factory=dict)
    unread: list[str] = Field(default_factory=list)


type SearchMetadataReader = Callable[[str], Awaitable[WDKProbe]]
"""Answers one search's expanded metadata document, or raises."""


def report_path() -> Path:
    named = os.environ.get(_REPORT_ENV)
    return Path(named) if named else _DEFAULT_REPORT


def load_report() -> SweepReport:
    path = report_path()
    if path.exists():
        return SweepReport.model_validate_json(path.read_text())
    return SweepReport(site=SITE)


class _PublishedParam(CamelModel):
    """One parameter of a search, as the expanded search document publishes it."""

    model_config = ConfigDict(extra="ignore")

    name: str
    type: str
    initial_display_value: str = ""
    is_visible: bool = True
    allow_empty_value: bool = False

    @field_validator("initial_display_value", mode="before")
    @classmethod
    def _a_default_of_any_type_is_read_as_its_text(cls, value: object) -> str:
        return "" if value is None else str(value)


class _SearchData(CamelModel):
    model_config = ConfigDict(extra="ignore")

    parameters: list[_PublishedParam] = Field(default_factory=list)


class _SearchDocument(CamelModel):
    model_config = ConfigDict(extra="ignore")

    search_data: _SearchData = Field(default_factory=_SearchData)


class _AnswerMeta(CamelModel):
    model_config = ConfigDict(extra="ignore")

    total_count: int | None = None


class _AnswerBody(CamelModel):
    model_config = ConfigDict(extra="ignore")

    meta: _AnswerMeta = Field(default_factory=_AnswerMeta)


def _required_params(document: JsonValue) -> list[HiddenParam]:
    """Every required parameter of a search, with the default it publishes."""
    try:
        parsed = _SearchDocument.model_validate(document)
    except pydantic.ValidationError:
        return []
    return [
        HiddenParam(
            name=param.name,
            param_type=param.type,
            default=param.initial_display_value,
            visible=param.is_visible,
        )
        for param in parsed.search_data.parameters
        if not param.allow_empty_value
    ]


def _total_count(probe: WDKProbe) -> int | None:
    """The count a standard report answered, or None when it answered no count."""
    if probe.status != 200:
        return None
    try:
        return _AnswerBody.model_validate(probe.json_body()).meta.total_count
    except pydantic.ValidationError:
        return None


async def measure(search: str, required: list[HiddenParam]) -> SearchMeasurement:
    """Run the search with every published default bound, and read the count."""
    hidden = [p for p in required if not p.visible and p.default]
    without_a_default = sorted(p.name for p in required if not p.default)
    if without_a_default:
        return SearchMeasurement(
            search=search,
            hidden=hidden,
            unmeasurable=without_a_default,
            note="a required parameter publishes no default",
        )

    bound = {p.name: p.default for p in required}
    client = get_wdk_client(SITE)
    try:
        result: WDKProbe = await client.probe(
            "POST",
            f"{TRANSCRIPT}/{search}/reports/standard",
            json={
                "searchConfig": {"parameters": bound},
                "reportConfig": {"pagination": {"offset": 0, "numRecords": 0}},
            },
        )
    except httpx.HTTPError as exc:
        # A search that never answers is not a search that answered nothing.
        return SearchMeasurement(
            search=search, hidden=hidden, bound=bound, note=type(exc).__name__
        )
    return SearchMeasurement(
        search=search,
        hidden=hidden,
        bound=bound,
        status=result.status,
        total_count=_total_count(result),
        note="" if result.status == 200 else result.text[:_NOTE_CHARS],
    )


async def hidden_by_search(
    read: SearchMetadataReader, names: list[str]
) -> MetadataSweep:
    """Read every search's metadata and keep the ones with a hidden default.

    A search whose metadata never arrives is named in ``unread`` and measured on
    a later run. The sweep resumes, so one transport failure is not a verdict on
    the rest of the searches.
    """
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def one(name: str) -> tuple[str, list[HiddenParam] | None]:
        async with semaphore:
            try:
                document = await read(name)
            except httpx.HTTPError:
                return name, None
        if document.status != 200:
            return name, []
        return name, _required_params(document.json_body())

    pairs = await asyncio.gather(*(one(name) for name in names))
    return MetadataSweep(
        hidden={
            name: required
            for name, required in pairs
            if required and any(not p.visible and p.default for p in required)
        },
        unread=[name for name, required in pairs if required is None],
    )
