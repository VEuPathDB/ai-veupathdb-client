"""The half of the WDK rules that only a running site can answer.

Every check here measures WDK, not this package. A failure means the platform
moved, which is what the lane exists to notice.
"""

from __future__ import annotations

import pytest
from tests.live.conftest import VERIFICATION_SITES, Probe

from veupathdb.testing.summary import DriftLog

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_TRANSCRIPT = "/record-types/transcript/searches"
_BOOLEAN = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


@pytest.mark.parametrize("site", VERIFICATION_SITES)
class TestWdkSearch001TheRecordTypeIsPartOfTheAddress:
    async def test_wdk_search_001_the_wrong_record_type_is_a_404_live(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            site, "GET", "/record-types/organism/searches/GenesByMolecularWeight"
        )

        drift_log.record(
            site=site,
            check="wrong-record-type-is-404",
            subject="organism/GenesByMolecularWeight",
            expected=404,
            observed=result.status,
        )
        assert result.status == 404
        assert "is no search" in result.text


@pytest.mark.parametrize("site", VERIFICATION_SITES)
class TestWdkSearch002TheFullNameIsNotAPathSegment:
    async def test_wdk_search_002_the_full_name_is_a_404_live(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            site, "GET", f"{_TRANSCRIPT}/GeneQuestions.GenesByMolecularWeight"
        )

        drift_log.record(
            site=site,
            check="full-name-is-404",
            subject="GeneQuestions.GenesByMolecularWeight",
            expected=404,
            observed=result.status,
        )
        assert result.status == 404

    async def test_wdk_search_002_the_url_segment_resolves_live(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(site, "GET", f"{_TRANSCRIPT}/GenesByMolecularWeight")

        drift_log.record(
            site=site,
            check="url-segment-resolves",
            subject="GenesByMolecularWeight",
            expected=200,
            observed=result.status,
        )
        assert result.status == 200


class TestWdkSearch003AvailabilityIsPerDeployment:
    async def test_wdk_search_003_the_two_sites_publish_different_sets(
        self, probe: Probe, drift_log: DriftLog
    ) -> None:
        counts: dict[str, int] = {}
        for site in VERIFICATION_SITES:
            result = await probe(site, "GET", _TRANSCRIPT)
            assert result.status == 200
            body = result.json_body()
            assert isinstance(body, list)
            counts[site] = len(body)
            drift_log.record(
                site=site,
                check="transcript-search-count",
                subject="record-types/transcript/searches",
                observed=len(body),
            )

        assert counts["plasmodb"] != counts["toxodb"]


@pytest.mark.parametrize("site", VERIFICATION_SITES)
class TestWdkHttp002TheStatusIsTheDiagnosis:
    async def test_wdk_http_002_every_error_body_is_text_plain_live(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(site, "GET", f"{_TRANSCRIPT}/NoSuchSearch")

        drift_log.record(
            site=site,
            check="error-content-type",
            subject="404 body",
            expected="text/plain",
            observed=result.content_type.split(";")[0],
        )
        assert result.status == 404
        assert result.content_type.startswith("text/plain")

    async def test_wdk_http_002_a_422_carries_json_under_text_plain_live(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            site,
            "POST",
            f"{_TRANSCRIPT}/GenesByLocation/refreshed-dependent-params",
            json={
                "changedParam": {"name": "organismSinglePick", "value": "Nope"},
                "contextParamValues": {"organismSinglePick": "Nope"},
            },
        )

        drift_log.record(
            site=site,
            check="refused-value-is-422",
            subject="GenesByLocation.organismSinglePick",
            expected=422,
            observed=result.status,
        )
        assert result.status == 422
        assert result.content_type.startswith("text/plain")
        assert result.json_body() is not None


@pytest.mark.parametrize("site", VERIFICATION_SITES)
class TestWdkVocab006TheRefusalsSplitLive:
    async def test_wdk_vocab_006_a_missing_changed_param_is_a_400_live(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            site,
            "POST",
            f"{_TRANSCRIPT}/GenesByLocation/refreshed-dependent-params",
            json={"contextParamValues": {}},
        )

        drift_log.record(
            site=site,
            check="missing-changed-param-is-400",
            subject="GenesByLocation",
            expected=400,
            observed=result.status,
        )
        assert result.status == 400

    async def test_wdk_vocab_006_a_non_string_value_is_a_400_live(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            site,
            "POST",
            f"{_TRANSCRIPT}/GenesByLocation/refreshed-dependent-params",
            json={
                "changedParam": {"name": "organismSinglePick", "value": ["Nope"]},
                "contextParamValues": {"organismSinglePick": "Nope"},
            },
        )

        drift_log.record(
            site=site,
            check="non-string-value-is-400",
            subject="GenesByLocation.organismSinglePick",
            expected=400,
            observed=result.status,
        )
        assert result.status == 400


@pytest.mark.parametrize("site", VERIFICATION_SITES)
class TestWdkParam001TheTwoAxesAreIndependent:
    async def test_wdk_param_001_a_multi_pick_is_drawn_as_a_select_live(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            site,
            "GET",
            f"{_TRANSCRIPT}/GenesByLocation",
            params={"expandParams": "true"},
        )
        assert result.status == 200
        body = result.json_body()
        assert isinstance(body, dict)
        params = {p["name"]: p for p in body["searchData"]["parameters"]}
        organism = params["organismSinglePick"]

        drift_log.record(
            site=site,
            check="organismSinglePick-type",
            subject="GenesByLocation.organismSinglePick",
            expected="multi-pick-vocabulary/select",
            observed=f"{organism['type']}/{organism.get('displayType')}",
        )
        assert organism["type"] == "multi-pick-vocabulary"
        assert organism["displayType"] == "select"


@pytest.mark.parametrize("site", VERIFICATION_SITES)
class TestWdkStep006And008TheBooleanSearch:
    async def test_wdk_step_006_the_operand_names_embed_the_full_name_live(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            site, "GET", f"{_TRANSCRIPT}/{_BOOLEAN}", params={"expandParams": "true"}
        )
        assert result.status == 200
        body = result.json_body()
        assert isinstance(body, dict)
        names = body["searchData"]["paramNames"]

        drift_log.record(
            site=site,
            check="boolean-param-names",
            subject=_BOOLEAN,
            expected=(
                "['bq_left_op_TranscriptRecordClasses_TranscriptRecordClass', "
                "'bq_right_op_TranscriptRecordClasses_TranscriptRecordClass', "
                "'bq_operator']"
            ),
            observed=names,
        )
        assert names == [
            "bq_left_op_TranscriptRecordClasses_TranscriptRecordClass",
            "bq_right_op_TranscriptRecordClasses_TranscriptRecordClass",
            "bq_operator",
        ]

    async def test_wdk_step_008_both_operands_take_one_record_class_live(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            site, "GET", f"{_TRANSCRIPT}/{_BOOLEAN}", params={"expandParams": "true"}
        )
        assert result.status == 200
        body = result.json_body()
        assert isinstance(body, dict)
        search = body["searchData"]

        drift_log.record(
            site=site,
            check="boolean-allowed-inputs",
            subject=_BOOLEAN,
            expected="['transcript']/['transcript']/transcript",
            observed=(
                f"{search['allowedPrimaryInputRecordClassNames']}/"
                f"{search['allowedSecondaryInputRecordClassNames']}/"
                f"{search['outputRecordClassName']}"
            ),
        )
        assert search["allowedPrimaryInputRecordClassNames"] == ["transcript"]
        assert search["allowedSecondaryInputRecordClassNames"] == ["transcript"]
        assert search["outputRecordClassName"] == "transcript"


@pytest.mark.parametrize("site", VERIFICATION_SITES)
class TestWdkAns006AnEmptyScopeStillRuns:
    async def test_wdk_ans_006_a_reporter_scoped_nowhere_answers_live(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            site,
            "POST",
            f"{_TRANSCRIPT}/GenesByMolecularWeight/reports/standard",
            json={
                "searchConfig": {
                    "parameters": {
                        "organism": '["Plasmodium falciparum 3D7"]'
                        if site == "plasmodb"
                        else '["Toxoplasma gondii ME49"]',
                        "min_molecular_weight": "10000",
                        "max_molecular_weight": "20000",
                    }
                },
                "reportConfig": {"pagination": {"offset": 0, "numRecords": 0}},
            },
        )

        drift_log.record(
            site=site,
            check="standard-report-runs",
            subject="GenesByMolecularWeight",
            expected=200,
            observed=result.status,
        )
        assert result.status == 200


class TestWdkSite007TheRadioPairIsPublished:
    """The pair is a property of the deployment's search, so only a site answers."""

    async def test_wdk_site_007_the_pair_travels_in_the_properties_live(
        self, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            "plasmodb", "GET", f"{_TRANSCRIPT}/GenesByGoTerm?expandParams=true"
        )
        assert result.status == 200
        body = result.json_body()
        assert isinstance(body, dict)
        search = body["searchData"]
        assert isinstance(search, dict)
        properties = search["properties"]
        assert isinstance(properties, dict)
        pair = properties["radio-params"]

        drift_log.record(
            site="plasmodb",
            check="radio-params-pair",
            subject="GenesByGoTerm",
            expected=["go_typeahead", "go_term"],
            observed=pair,
        )
        assert pair == ["go_typeahead", "go_term"]
