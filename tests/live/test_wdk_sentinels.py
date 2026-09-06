"""Whether the science PathFinder relies on is still there.

A sentinel is a named search, a pinned vocabulary value, or a count PathFinder
builds strategies out of. Counts move with each data release, so a count is
checked against a band rather than a number.
"""

from __future__ import annotations

import pytest
from pydantic import JsonValue, TypeAdapter
from tests.live.conftest import VERIFICATION_SITES, Probe

from veupathdb.domain.parameters.wdk_vocab import WDKVocabulary, vocab_keys
from veupathdb.testing.summary import DriftLog

_VOCABULARY: TypeAdapter[WDKVocabulary] = TypeAdapter(WDKVocabulary)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_TRANSCRIPT = "/record-types/transcript/searches"

# Searches PathFinder names in prompts, tests and the gold corpus.
_REQUIRED_SEARCHES = (
    "GenesByText",
    "GenesByGoTerm",
    "GenesByMolecularWeight",
    "GenesByLocation",
    "GenesByExonCount",
    "GenesByTaxon",
    "GenesBySpanLogic",
    "GenesByOrthologs",
    "GenesByOrthologPattern",
    "GeneByLocusTag",
)

# One organism per site, as the vocabulary spells it.
_PINNED_ORGANISM = {
    "plasmodb": "Plasmodium falciparum 3D7",
    "toxodb": "Toxoplasma gondii ME49",
}

# A kinase set measured at 105 genes. The band absorbs a data release.
_KINASE_TERM = "GO:0004672"
_KINASE_BAND = (60, 200)


def _params(body: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(body, dict)
    return {p["name"]: p for p in body["searchData"]["parameters"]}


def _terms(vocabulary: JsonValue) -> set[str]:
    """The terms of a vocabulary, flat or treeBox."""
    parsed = _VOCABULARY.validate_python(vocabulary)
    return vocab_keys(parsed)


@pytest.mark.parametrize("site", VERIFICATION_SITES)
class TestTheSearchesPathFinderNamesExist:
    @pytest.mark.parametrize("search", _REQUIRED_SEARCHES)
    async def test_a_named_search_is_still_published(
        self, site: str, search: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(site, "GET", f"{_TRANSCRIPT}/{search}")

        drift_log.record(
            site=site,
            check="search-exists",
            subject=search,
            expected=200,
            observed=result.status,
        )
        assert result.status == 200


@pytest.mark.parametrize("site", VERIFICATION_SITES)
class TestThePinnedVocabularyValuesAreStillThere:
    async def test_the_pinned_organism_is_still_a_term(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            site,
            "GET",
            f"{_TRANSCRIPT}/GenesByMolecularWeight",
            params={"expandParams": "true"},
        )
        assert result.status == 200
        terms = _terms(_params(result.json_body())["organism"]["vocabulary"])

        drift_log.record(
            site=site,
            check="organism-term-present",
            subject=_PINNED_ORGANISM[site],
            expected=True,
            observed=_PINNED_ORGANISM[site] in terms,
        )
        assert _PINNED_ORGANISM[site] in terms

    async def test_the_exon_scope_terms_are_still_two(
        self, site: str, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            site,
            "GET",
            f"{_TRANSCRIPT}/GenesByExonCount",
            params={"expandParams": "true"},
        )
        assert result.status == 200
        terms = sorted(_terms(_params(result.json_body())["scope"]["vocabulary"]))

        drift_log.record(
            site=site,
            check="exon-scope-terms",
            subject="GenesByExonCount.scope",
            expected="['Gene', 'Transcript']",
            observed=terms,
        )
        assert terms == ["Gene", "Transcript"]


class TestTheSentinelCountsAreInBand:
    async def test_the_kinase_go_term_still_returns_a_gene_set(
        self, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            "plasmodb",
            "POST",
            f"{_TRANSCRIPT}/GenesByGoTerm/reports/standard",
            json={
                "searchConfig": {
                    "parameters": {
                        "organism": f'["{_PINNED_ORGANISM["plasmodb"]}"]',
                        "go_term_evidence": '["Curated","Computed"]',
                        "go_term_slim": "No",
                        "go_typeahead": f'["{_KINASE_TERM}"]',
                        "go_term": _KINASE_TERM,
                    }
                },
                "reportConfig": {"pagination": {"offset": 0, "numRecords": 0}},
            },
        )
        assert result.status == 200, result.text[:300]
        body = result.json_body()
        assert isinstance(body, dict)
        count = int(body["meta"]["totalCount"])

        low, high = _KINASE_BAND
        drift_log.record(
            site="plasmodb",
            check="kinase-count-in-band",
            subject=f"GenesByGoTerm {_KINASE_TERM}",
            observed=count,
        )
        assert low <= count <= high

    async def test_a_text_search_still_returns_a_gene_set(
        self, probe: Probe, drift_log: DriftLog
    ) -> None:
        result = await probe(
            "plasmodb",
            "POST",
            f"{_TRANSCRIPT}/GenesByText/reports/standard",
            json={
                "searchConfig": {
                    "parameters": {
                        "text_expression": "kinase",
                        "text_fields": '["product"]',
                        "document_type": "gene",
                        "text_search_organism": (f'["{_PINNED_ORGANISM["plasmodb"]}"]'),
                    }
                },
                "reportConfig": {"pagination": {"offset": 0, "numRecords": 0}},
            },
        )
        assert result.status == 200, result.text[:300]
        body = result.json_body()
        assert isinstance(body, dict)
        count = int(body["meta"]["totalCount"])

        drift_log.record(
            site="plasmodb",
            check="text-search-is-not-empty",
            subject="GenesByText product=kinase",
            observed=count,
        )
        assert count > 0
