"""The site model parameter rules: the phyletic census pattern and the radio pair."""

from __future__ import annotations

from veupathdb.domain.parameters.phyletic import (
    NO_CONSTRAINT_PATTERN,
    encode_profile_pattern,
    read_census,
    sort_profile_pattern,
)
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearch


def test_wdk_site_001_the_pattern_wraps_and_separates_its_tokens_with_the_wildcard() -> (
    None
):
    """The `%` is the LIKE wildcard, not a separator, so it wraps as well as joins."""
    written = encode_profile_pattern({"atum": "include", "auva": "exclude"})

    assert written == "%atum:Y%auva:N%"
    assert encode_profile_pattern({}) == NO_CONSTRAINT_PATTERN


def test_wdk_site_002_an_included_species_is_written_as_the_matching_state() -> None:
    """A wrong state is never refused by WDK, so the encoder states it."""
    written = encode_profile_pattern({"pfal": "include", "hsap": "exclude"})
    read = read_census(written)

    assert "pfal:Y" in written
    assert "hsap:N" in written
    assert read.states == {"pfal": "include", "hsap": "exclude"}


def test_wdk_site_004_the_tokens_are_written_in_ascending_code_order() -> None:
    """The census lists codes ascending, so tokens out of order match nothing."""
    assert sort_profile_pattern("%pfal:Y%atum:N%") == "%atum:N%pfal:Y%"


def test_wdk_site_007_a_search_carries_the_properties_the_deployment_sent() -> None:
    """A radio pair travels in `properties`, which the parse leaves as it is sent."""
    body = load_recorded("search_genes_by_molecular_weight").json_body()
    assert isinstance(body, dict)
    sent = body["searchData"]
    assert isinstance(sent, dict)

    search = WDKSearch.model_validate(sent)

    assert search.properties == sent["properties"]
    assert search.properties["organisms"] == [
        "P. falciparum",
        "P. vivax",
        "P. yoelii",
        "P. berghei",
        "P. chabaudi",
        "P. knowlesi",
    ]
