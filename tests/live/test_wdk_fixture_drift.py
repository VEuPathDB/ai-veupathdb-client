"""Whether the pinned fixtures still describe the live sites.

A failure here is the signal to re-record:
``python -m veupathdb.devtools.fixtures record``.
"""

from __future__ import annotations

import pytest
from pydantic import JsonValue
from tests.live.conftest import Probe

from veupathdb.testing.summary import DriftLog
from veupathdb.testing.wdk_fixtures import FIXTURES, FixtureRequest, load_recorded

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]


def _shape(body: JsonValue) -> str:
    """The keys a body carries, which is what a hermetic test reads."""
    match body:
        case {**fields}:
            return ",".join(sorted(fields))
        case [*items]:
            return f"list[{len(items)}]"
        case _:
            return type(body).__name__


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.name)
class TestThePinnedFixturesStillHold:
    async def test_the_status_is_unchanged(
        self, fixture: FixtureRequest, probe: Probe, drift_log: DriftLog
    ) -> None:
        recorded = load_recorded(fixture.name)
        live = await probe(
            fixture.site,
            fixture.method,
            fixture.path,
            params=dict(fixture.params),
            json=fixture.body,
        )

        drift_log.record(
            site=fixture.site,
            check="fixture-status",
            subject=fixture.name,
            expected=recorded.provenance.status,
            observed=live.status,
        )
        assert live.status == recorded.provenance.status

    async def test_the_content_type_is_unchanged(
        self, fixture: FixtureRequest, probe: Probe, drift_log: DriftLog
    ) -> None:
        recorded = load_recorded(fixture.name)
        live = await probe(
            fixture.site,
            fixture.method,
            fixture.path,
            params=dict(fixture.params),
            json=fixture.body,
        )

        drift_log.record(
            site=fixture.site,
            check="fixture-content-type",
            subject=fixture.name,
            expected=recorded.provenance.content_type,
            observed=live.content_type,
        )
        assert live.content_type == recorded.provenance.content_type

    async def test_the_body_shape_is_unchanged(
        self, fixture: FixtureRequest, probe: Probe, drift_log: DriftLog
    ) -> None:
        recorded = load_recorded(fixture.name)
        live = await probe(
            fixture.site,
            fixture.method,
            fixture.path,
            params=dict(fixture.params),
            json=fixture.body,
        )
        live_body = live.json_body()
        pinned = recorded.body if live_body is not None else recorded.raw_text()
        observed = _shape(live_body) if live_body is not None else _shape(live.text)

        drift_log.record(
            site=fixture.site,
            check="fixture-body-shape",
            subject=fixture.name,
            expected=_shape(pinned),
            observed=observed,
        )
        assert observed == _shape(pinned)
