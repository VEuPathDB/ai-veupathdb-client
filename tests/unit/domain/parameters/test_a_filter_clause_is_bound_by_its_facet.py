"""A filter clause takes its type and isRange from the facet it names."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from veupathdb.domain.parameters import (
    DateBounds,
    DateRange,
    FacetRange,
    FilterFacet,
    FilterFacets,
    FilterProposals,
    FilterStatementError,
    FilterValue,
    NumberBounds,
    NumberRange,
    StringMembers,
)
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKOntologyTermSummary, WDKParameter, WDKSearchResponse


def _filter_param(fixture: str, name: str) -> WDKParameter:
    search = WDKSearchResponse.model_validate(load_recorded(fixture).json_body())
    return next(p for p in search.search_data.parameters or [] if p.name == name)


def _samples() -> FilterFacets:
    return FilterFacets.of(
        _filter_param("search_genes_by_ngs_snps", "variation_sample_meta")
    )


def _variant_stats() -> FilterFacets:
    return FilterFacets.of(
        _filter_param("search_genes_by_variant_characteristics", "gene_variant_stats")
    )


def _bind(facets: FilterFacets, raw: object) -> FilterValue:
    return facets.bind(FilterProposals.model_validate(raw))


def _refusal(facets: FilterFacets, raw: object) -> str:
    with pytest.raises(FilterStatementError) as refused:
        _bind(facets, raw)
    return str(refused.value.detail)


def _facet(facets: FilterFacets, name: str) -> FilterFacet:
    facet = facets.find(name)
    assert facet is not None
    return facet


def _summary(fixture: str) -> WDKOntologyTermSummary:
    return WDKOntologyTermSummary.model_validate(load_recorded(fixture).json_body())


class TestAMemberFacet:
    def test_a_display_name_binds_the_term_as_a_string_clause(self) -> None:
        value = _bind(_samples(), [{"field": "sex", "value": ["female"]}])

        assert value.filters == [
            StringMembers(
                field="VAR_68bb04bd",
                type="string",
                is_range=False,
                include_unknown=False,
                value=["female"],
            )
        ]

    def test_a_member_the_facet_does_not_hold_is_refused_with_its_members(
        self,
    ) -> None:
        text = _refusal(_samples(), [{"field": "sex", "value": ["hermaphrodite"]}])

        assert "female, male" in text

    def test_include_unknown_is_carried(self) -> None:
        value = _bind(
            _samples(),
            [{"field": "country", "value": ["Togo"], "includeUnknown": True}],
        )

        assert [clause.include_unknown for clause in value.filters] == [True]


class TestARangeFacet:
    def test_a_date_facet_binds_a_date_range(self) -> None:
        value = _bind(
            _samples(), [{"field": "Collection date", "value": {"min": "2015-01-01"}}]
        )

        assert value.filters == [
            DateRange(
                field="VAR_338f1760",
                type="date",
                is_range=True,
                include_unknown=False,
                value=DateBounds(min="2015-01-01", max=None),
            )
        ]

    def test_a_date_bound_that_is_not_iso_is_refused(self) -> None:
        text = _refusal(
            _samples(), [{"field": "Collection date", "value": {"min": "20150101"}}]
        )

        assert "yyyy-mm-dd" in text

    def test_a_number_facet_binds_a_number_range(self) -> None:
        value = _bind(
            _variant_stats(), [{"field": "total_variants", "value": {"min": 6}}]
        )

        assert value.filters == [
            NumberRange(
                field="total_variants",
                type="number",
                is_range=True,
                include_unknown=False,
                value=NumberBounds(min=6, max=None),
            )
        ]

    def test_a_list_on_a_range_facet_is_refused_with_its_form(self) -> None:
        text = _refusal(
            _variant_stats(), [{"field": "total_variants", "value": ["0", "0.05"]}]
        )

        assert (
            'total_variants (Total variants) takes {"field": "total_variants", '
            '"value": {"min": <n>, "max": <n>}} with either bound left out'
        ) in text

    def test_the_bound_value_dumps_the_clause_wdk_parses(self) -> None:
        value = _bind(
            _variant_stats(), [{"field": "total_variants", "value": {"min": 6}}]
        )

        assert value.to_decoded() == {
            "filters": [
                {
                    "field": "total_variants",
                    "type": "number",
                    "isRange": True,
                    "includeUnknown": False,
                    "value": {"min": 6.0},
                }
            ]
        }


class TestAFacetIsFoundByItsExactName:
    def test_a_substring_finds_no_facet(self) -> None:
        assert _variant_stats().find("variants") is None

    def test_a_display_name_finds_its_term(self) -> None:
        assert _facet(_variant_stats(), "Total variants").term == "total_variants"

    def test_an_unknown_name_is_refused_with_every_facet_term(self) -> None:
        facets = _variant_stats()

        text = _refusal(facets, [{"field": "variants", "value": {"min": 1}}])

        assert len(facets.root) == 16
        assert all(facet.term in text for facet in facets.root)

    def test_every_fault_is_one_error_with_a_line_each(self) -> None:
        text = _refusal(
            _variant_stats(),
            [
                {"field": "variants", "value": {"min": 1}},
                {"field": "total_variants", "value": ["0"]},
            ],
        )

        assert len(text.splitlines()) == 2


class TestAStatementIsAListOfClauses:
    def test_an_empty_list_is_refused(self) -> None:
        with pytest.raises(PydanticValidationError):
            FilterProposals.model_validate([])

    def test_the_shorthand_is_refused(self) -> None:
        with pytest.raises(PydanticValidationError):
            FilterProposals.model_validate("total_variants>5")

    def test_a_stored_clause_states_its_type_and_is_range(self) -> None:
        with pytest.raises(PydanticValidationError):
            FilterValue.model_validate({"filters": [{"field": "x", "value": ["a"]}]})


class TestAHeldValue:
    def test_a_clause_the_facets_hold_is_kept(self) -> None:
        facets = _samples()
        value = _bind(facets, [{"field": "sex", "value": ["male"]}])

        assert facets.held(value) == value

    def test_a_clause_the_facets_do_not_hold_is_refused(self) -> None:
        stored = _bind(_samples(), [{"field": "sex", "value": ["male"]}])

        with pytest.raises(FilterStatementError):
            _variant_stats().held(stored)


class TestAFacetRange:
    def test_a_number_range_is_read_from_the_term_summary(self) -> None:
        facet = _facet(_variant_stats(), "total_variants")

        span = FacetRange.of(_summary("ontology_term_summary_total_variants"), facet)

        assert span == FacetRange(min=1, max=4823, records=5643, units="variants")
        assert span.text() == "1 to 4,823 variants over 5,643 records"

    def test_a_range_past_the_largest_value_selects_nothing(self) -> None:
        facet = _facet(_variant_stats(), "total_variants")
        span = FacetRange.of(_summary("ontology_term_summary_total_variants"), facet)

        assert span is not None
        assert span.selects(NumberBounds(min=4824, max=None)) is False
        assert span.selects(NumberBounds(min=4823, max=None)) is True

    def test_a_date_range_is_read_as_iso_dates(self) -> None:
        facet = _facet(_samples(), "Collection date")

        span = FacetRange.of(
            _summary("ontology_term_summary_ngs_snps_collection_date"), facet
        )

        assert span == FacetRange(
            min="2001-11-22", max="2014-08-30", records=200, units=None
        )

    def test_a_summary_with_no_counted_value_has_no_range(self) -> None:
        facet = _facet(_variant_stats(), "total_variants")
        empty = WDKOntologyTermSummary(
            value_counts=[], internals_count=0, internals_filtered_count=0
        )

        assert FacetRange.of(empty, facet) is None


def test_an_ontology_term_reads_its_units() -> None:
    param = _filter_param(
        "search_genes_by_variant_characteristics", "gene_variant_stats"
    )

    assert {term.term: term.units for term in param.ontology}["variants_per_kb"] == (
        "variants/kb"
    )
