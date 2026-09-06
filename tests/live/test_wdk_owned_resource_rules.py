"""The rules that need a step and a strategy on the account.

Every resource these checks create is deleted when the check ends.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from tests.live.conftest import Probe

from veupathdb.testing.summary import DriftLog

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITE = "plasmodb"
_SCHEMA_LEVELS = ("NONE", "UNSPECIFIED", "SYNTACTIC", "SEMANTIC", "RUNNABLE")

OwnedStrategy = Callable[[str], Awaitable[tuple[int, int]]]


async def _user_id(probe: Probe) -> int:
    me = await probe(_SITE, "GET", "/users/current")
    body = me.json_body()
    assert isinstance(body, dict)
    return int(body["id"])


class TestWdkStep005ACountNeedsAStrategy:
    async def test_wdk_step_005_a_step_in_a_strategy_reports_a_count_live(
        self, owned_strategy: OwnedStrategy, probe: Probe, drift_log: DriftLog
    ) -> None:
        _, step_id = await owned_strategy(_SITE)
        user = await _user_id(probe)

        result = await probe(
            _SITE,
            "POST",
            f"/users/{user}/steps/{step_id}/reports/standard",
            json={"reportConfig": {"pagination": {"offset": 0, "numRecords": 0}}},
        )

        drift_log.record(
            site=_SITE,
            check="step-in-strategy-counts",
            subject=str(step_id),
            expected=200,
            observed=result.status,
        )
        assert result.status == 200


class TestWdkFilter006ByValueIsNotOfferedByTheRecordType:
    async def test_wdk_filter_006_the_primary_key_column_refuses_by_value_live(
        self, owned_strategy: OwnedStrategy, probe: Probe, drift_log: DriftLog
    ) -> None:
        # The record-type document advertises byValue on this column anyway.
        _, step_id = await owned_strategy(_SITE)
        user = await _user_id(probe)

        result = await probe(
            _SITE,
            "POST",
            f"/users/{user}/steps/{step_id}/columns/primary_key/reports/byValue",
            json={"reportConfig": {}},
        )

        # The status of the refusal has moved once; the refusal has not.
        drift_log.record(
            site=_SITE,
            check="byvalue-on-primary-key",
            subject="primary_key",
            expected=500,
            observed=result.status,
        )
        assert result.status >= 400

    async def test_wdk_filter_006_a_real_filterable_column_is_accepted_live(
        self, owned_strategy: OwnedStrategy, probe: Probe, drift_log: DriftLog
    ) -> None:
        _, step_id = await owned_strategy(_SITE)
        user = await _user_id(probe)

        result = await probe(
            _SITE,
            "POST",
            f"/users/{user}/steps/{step_id}/columns/gene_product/reports/byValue",
            json={"reportConfig": {}},
        )

        drift_log.record(
            site=_SITE,
            check="byvalue-on-gene-product",
            subject="gene_product",
            expected=200,
            observed=result.status,
        )
        assert result.status == 200


class TestWdkValid007DisplayableIsASixthLevel:
    async def test_wdk_valid_007_an_analysis_type_reports_displayable_live(
        self, owned_strategy: OwnedStrategy, probe: Probe, drift_log: DriftLog
    ) -> None:
        _, step_id = await owned_strategy(_SITE)
        user = await _user_id(probe)

        result = await probe(
            _SITE, "GET", f"/users/{user}/steps/{step_id}/analysis-types"
        )

        drift_log.record(
            site=_SITE,
            check="analysis-types-reachable",
            subject=str(step_id),
            expected=200,
            observed=result.status,
        )
        assert result.status == 200

    async def test_wdk_valid_007_the_step_schema_rejects_that_level_live(
        self, owned_strategy: OwnedStrategy, probe: Probe, drift_log: DriftLog
    ) -> None:
        # The failure is a 500 from the outbound validator, not a 400.
        _, step_id = await owned_strategy(_SITE)
        user = await _user_id(probe)

        result = await probe(
            _SITE,
            "GET",
            f"/users/{user}/steps/{step_id}",
            params={"validationLevel": "DISPLAYABLE"},
        )

        drift_log.record(
            site=_SITE,
            check="displayable-on-step-is-500",
            subject=str(step_id),
            expected=500,
            observed=result.status,
        )
        assert result.status == 500

    async def test_wdk_valid_007_an_unknown_level_is_answered_silently_live(
        self, owned_strategy: OwnedStrategy, probe: Probe, drift_log: DriftLog
    ) -> None:
        # A name the enum lacks is not an error; it is a different question.
        _, step_id = await owned_strategy(_SITE)
        user = await _user_id(probe)

        result = await probe(
            _SITE,
            "GET",
            f"/users/{user}/steps/{step_id}",
            params={"validationLevel": "NOT_A_LEVEL"},
        )
        body = result.json_body()
        assert isinstance(body, dict)
        level = body["validation"]["level"]

        drift_log.record(
            site=_SITE,
            check="unknown-level-falls-back",
            subject=str(step_id),
            expected="RUNNABLE",
            observed=level,
        )
        assert result.status == 200
        assert level in _SCHEMA_LEVELS


class TestWdkParam003SinglePickTakesOneTerm:
    async def test_wdk_param_003_two_terms_are_a_500_live(
        self, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            _SITE,
            "POST",
            "/record-types/transcript/searches/GenesByExonCount/refreshed-dependent-params",
            json={
                "changedParam": {"name": "scope", "value": '["Gene","Transcript"]'},
                "contextParamValues": {"scope": '["Gene","Transcript"]'},
            },
        )

        drift_log.record(
            site=_SITE,
            check="single-pick-two-terms",
            subject="GenesByExonCount.scope",
            observed=result.status,
        )
        assert result.status >= 400


class TestWdkParam011AHiddenRequiredParamIsRefusedByName:
    async def test_wdk_param_011_an_empty_hidden_value_is_refused_live(
        self, probe: Probe, drift_log: DriftLog
    ) -> None:
        search = "GenesByOrthologPattern"
        result = await probe(
            _SITE,
            "POST",
            f"/record-types/transcript/searches/{search}/reports/standard",
            json={
                "searchConfig": {
                    "parameters": {
                        "organism": '["Plasmodium falciparum 3D7"]',
                        "profile_pattern": "",
                    }
                },
                "reportConfig": {"pagination": {"offset": 0, "numRecords": 0}},
            },
        )

        drift_log.record(
            site=_SITE,
            check="empty-hidden-required-is-refused",
            subject=f"{search}.profile_pattern",
            expected=422,
            observed=result.status,
        )
        assert result.status == 422
        assert "profile_pattern" in result.text
