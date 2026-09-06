"""Which hidden required defaults return rows, and which return nothing.

The sweep is long, so it is resumable: a completed search is read back from the
report file rather than asked again. ``WDK_HIDDEN_DEFAULTS_REPORT`` names the
file, ``WDK_HIDDEN_DEFAULTS_LIMIT`` caps how many searches one run measures.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from tests.live.conftest import Probe
from tests.live.hidden_defaults import (
    LIMIT_ENV,
    SITE,
    TRANSCRIPT,
    SearchMeasurement,
    SearchMetadataReader,
    hidden_by_search,
    load_report,
    measure,
    report_path,
)

from veupathdb.testing.summary import DriftLog
from veupathdb.wdk.probe import WDKProbe

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_CONCURRENCY = 6


async def _collect_searches(probe: Probe) -> list[str]:
    listing = await probe(SITE, "GET", TRANSCRIPT)
    assert listing.status == 200
    body = listing.json_body()
    assert isinstance(body, list)
    return [str(entry["urlSegment"]) for entry in body if isinstance(entry, dict)]


def _metadata_reader(probe: Probe) -> SearchMetadataReader:
    async def read(name: str) -> WDKProbe:
        return await probe(
            SITE, "GET", f"{TRANSCRIPT}/{name}", params={"expandParams": "true"}
        )

    return read


async def test_the_hidden_required_defaults_that_return_nothing_are_named(
    probe: Probe, drift_log: DriftLog
) -> None:
    """Measure every search whose hidden required parameters carry a default."""
    names = await _collect_searches(probe)
    sweep = await hidden_by_search(_metadata_reader(probe), names)
    assert len(sweep.unread) < len(names), "no search metadata arrived"

    report = load_report()
    outstanding = [s for s in sorted(sweep.hidden) if s not in report.measured]
    limit = int(os.environ.get(LIMIT_ENV, "0"))
    if limit > 0:
        outstanding = outstanding[:limit]

    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def one(search: str) -> SearchMeasurement:
        async with semaphore:
            return await measure(search, sweep.hidden[search])

    for measurement in await asyncio.gather(*(one(s) for s in outstanding)):
        report.measured[measurement.search] = measurement

    report_path().write_text(report.model_dump_json(indent=2) + "\n")

    empty = sorted(m.search for m in report.measured.values() if m.returned_nothing)
    drift_log.record(
        site=SITE,
        check="hidden-defaults-searches-carrying-one",
        subject="record-types/transcript",
        observed=len(sweep.hidden),
    )
    drift_log.record(
        site=SITE,
        check="hidden-defaults-metadata-unread",
        subject=json.dumps(sweep.unread[:20]),
        expected=0,
        observed=len(sweep.unread),
    )
    drift_log.record(
        site=SITE,
        check="hidden-defaults-returning-zero",
        subject=json.dumps(empty[:20]),
        expected=0,
        observed=len(empty),
    )

    # The sweep names them; whether a zero is wrong is a per-search question.
    assert report.measured, "the sweep measured nothing"
