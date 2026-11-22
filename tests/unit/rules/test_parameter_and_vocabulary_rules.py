"""The parameter and vocabulary rules, over the recorded search documents."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import TypeAdapter

from veupathdb.domain.parameters import (
    FacetRange,
    FilterFacets,
    FilterProposals,
    MultiPickValue,
    NumberBounds,
    NumberRange,
    ParameterCanonicalizer,
    ParamValue,
    SinglePickValue,
    StatedValuesError,
    StringMembers,
    StringValue,
    same_value,
)
from veupathdb.domain.parameters.dependencies import ParamGraph
from veupathdb.domain.parameters.specs import (
    ParamSpecNormalized,
    fill_site_set_defaults,
)
from veupathdb.domain.parameters.value_codec import to_wire
from veupathdb.domain.parameters.wdk_vocab import (
    FAKE_ALL_SENTINEL,
    WDKTreeBoxVocabNode,
    flatten_vocab,
)
from veupathdb.json_types import JSONObject
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKOntologyTermSummary, WDKParameter
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.wdk_models import WDKSearchResponse


def _recorded_parameters(name: str) -> dict[str, JSONObject]:
    body = load_recorded(name).json_body()
    assert isinstance(body, dict)
    search = body["searchData"]
    assert isinstance(search, dict)
    listed = search["parameters"]
    assert isinstance(listed, list)
    return {str(param["name"]): param for param in listed if isinstance(param, dict)}


def _parameter(fixture: str, name: str) -> WDKParameter:
    search = WDKSearchResponse.model_validate(load_recorded(fixture).json_body())
    return next(p for p in search.search_data.parameters or [] if p.name == name)


class _Echo:
    """Answers one recorded body and keeps what it was sent."""

    def __init__(self, body: Any) -> None:
        self._body = body
        self.sent: list[dict[str, Any]] = []

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> Any:
        del path
        self.sent.append(json or {})
        return self._body


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_molecular_weight.json"),
    reason=NEEDS_QA_RECORDING,
)
def test_wdk_param_007_a_numeric_bound_is_a_string_parameter_flagged_is_number() -> (
    None
):
    """The molecular-weight bounds arrive as `string`, not as a number type."""
    parameters = _recorded_parameters("search_genes_by_molecular_weight")
    bound = parameters["min_molecular_weight"]

    assert bound["type"] == "string"
    assert bound["isNumber"] is True
    with pytest.raises(StatedValuesError):
        _parameter(
            "search_genes_by_molecular_weight", "min_molecular_weight"
        ).read_stated("10,000")


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_location.json"), reason=NEEDS_QA_RECORDING
)
async def test_wdk_param_008_the_revise_endpoint_answer_is_what_wdk_substituted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client returns WDK's echoed values, never the context it sent."""
    body = load_recorded("search_genes_by_location").json_body()
    client = VEuPathDBClient("https://example.invalid/service")
    echo = _Echo(body)
    monkeypatch.setattr(client, "post", echo)

    response = await client.get_search_details_with_params(
        "transcript", "GenesByLocation", {"organismSinglePick": "a value WDK replaces"}
    )

    parameters = response.search_data.parameters or []
    sent = echo.sent[0]["contextParamValues"]["organismSinglePick"]
    assert sent == "a value WDK replaces"
    assert [param.name for param in parameters] == list(
        _recorded_parameters("search_genes_by_location")
    )


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_with_a_hidden_required_parameter.json"),
    reason=NEEDS_QA_RECORDING,
)
def test_wdk_param_011_a_hidden_required_parameter_is_filled_from_its_default() -> None:
    """`isVisible: false` hides the parameter; WDK still requires a value."""
    recorded = _recorded_parameters("search_with_a_hidden_required_parameter")
    hidden = recorded["eda_dataset_id"]
    spec = ParamSpecNormalized(
        name="eda_dataset_id",
        param_type=str(hidden["type"]),
        is_visible=bool(hidden["isVisible"]),
        allow_empty_value=bool(hidden["allowEmptyValue"]),
        initial_display_value=str(hidden["initialDisplayValue"]),
    )

    filled = fill_site_set_defaults({spec.name: spec}, {})

    assert hidden["isVisible"] is False
    assert to_wire(filled["eda_dataset_id"]) == hidden["initialDisplayValue"]


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_ngs_snps.json")
    or needs_qa_recording("wdk/search_genes_by_ngs_snps_under_another_organism.json")
    or needs_qa_recording("wdk/refresh_ngs_snps_on_organism.json"),
    reason=NEEDS_QA_RECORDING,
)
def test_wdk_param_016_a_site_set_dependent_follows_its_parents() -> None:
    """A hidden dependent takes the value its parents choose, not the published one."""
    published = _recorded_parameters("search_genes_by_ngs_snps")
    under_vivax = _recorded_parameters(
        "search_genes_by_ngs_snps_under_another_organism"
    )
    refreshed = TypeAdapter(list[JSONObject]).validate_python(
        load_recorded("refresh_ngs_snps_on_organism").json_body()
    )
    refreshed_by_name = {str(param["name"]): param for param in refreshed}
    graph = ParamGraph.of(
        WDKSearchResponse.model_validate(
            load_recorded("search_genes_by_ngs_snps").json_body()
        ).search_data.parameters
        or []
    )

    suffix = "eda_sample_table_suffix"
    assert published[suffix]["isVisible"] is False
    assert under_vivax["organismSinglePick"]["initialDisplayValue"] == (
        '["Plasmodium vivax P01"]'
    )
    assert published[suffix]["initialDisplayValue"] == "s3be28bbe14_sample"
    assert under_vivax[suffix]["initialDisplayValue"] == "sba1cd4a562_sample"
    assert refreshed_by_name[suffix]["initialDisplayValue"] == "sba1cd4a562_sample"
    assert published["organismSinglePick"]["initialDisplayValue"] == (
        '["Plasmodium falciparum 3D7"]'
    )
    assert graph.wire_parents[suffix] == ("organismSinglePick",)
    assert suffix in graph.wire_parents["variation_sample_meta"]
    assert graph.stated_parents["variation_sample_meta"] == ("organismSinglePick",)


def test_wdk_vocab_001_the_synthetic_root_is_not_a_selectable_term() -> None:
    """A tree whose root is `@@fake@@` offers its children and not the root."""
    tree = WDKTreeBoxVocabNode.model_validate(
        {
            "data": {"term": FAKE_ALL_SENTINEL, "display": "All"},
            "children": [
                {"data": {"term": "pfal", "display": "P. falciparum"}, "children": []}
            ],
        }
    )

    assert [option.value for option in flatten_vocab(tree)] == ["pfal"]


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_location.json"), reason=NEEDS_QA_RECORDING
)
def test_wdk_vocab_003_the_order_of_dependent_params_carries_nothing() -> None:
    """A parent fills before its dependents, whatever order the list arrived in."""
    recorded = _recorded_parameters("search_genes_by_location")
    parent = recorded["organismSinglePick"]
    dependents = TypeAdapter(list[str]).validate_python(parent["dependentParams"] or [])

    def specs(order: list[str]) -> list[ParamSpecNormalized]:
        return [
            ParamSpecNormalized(
                name="organismSinglePick",
                param_type="single-pick-vocabulary",
                dependent_params=tuple(order),
            ),
            ParamSpecNormalized(
                name="chromosomeOptional", param_type="single-pick-vocabulary"
            ),
        ]

    assert dependents == ["chromosomeOptional"]
    assert (
        ParamGraph.of(specs(dependents)).fill_order
        == ParamGraph.of(specs(list(reversed(dependents)))).fill_order
    )


async def test_wdk_vocab_004_a_dependent_value_travels_with_the_parent_it_was_read_under(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WDK accepts a dependent value under any parent, so the context is always sent."""
    client = VEuPathDBClient("https://example.invalid/service")
    echo = _Echo([])
    monkeypatch.setattr(client, "post", echo)

    await client.get_refreshed_dependent_params(
        "transcript",
        "GenesByLocation",
        "organismSinglePick",
        {"organismSinglePick": "P. falciparum", "chromosomeOptional": "Pf3D7_01_v3"},
    )

    sent = echo.sent[0]
    assert sent["changedParam"] == {
        "name": "organismSinglePick",
        "value": "P. falciparum",
    }
    assert sent["contextParamValues"]["chromosomeOptional"] == "Pf3D7_01_v3"


async def test_wdk_vocab_005_an_empty_array_names_no_stale_dependent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`200 []` is nothing to refresh, not every dependent cleared."""
    client = VEuPathDBClient("https://example.invalid/service")
    monkeypatch.setattr(client, "post", _Echo([]))

    refreshed = await client.get_refreshed_dependent_params(
        "transcript", "GenesByLocation", "organismSinglePick", {}
    )

    assert refreshed == []


@pytest.mark.parametrize(
    ("fixture", "marked"),
    [
        ("search_genes_by_molecular_weight", "organism"),
        ("search_genes_by_exon_count", "organism"),
        ("search_genes_by_gene_type", "organism"),
        ("search_genes_by_ortholog_pattern", "organism"),
        ("search_genes_by_orthologs", "organism"),
        ("search_genes_by_taxon", "organism"),
        ("search_genes_by_ngs_snps", "organismSinglePick"),
        ("search_genes_by_ngs_snps_under_another_organism", "organismSinglePick"),
        ("search_genes_by_location", "organismSinglePick"),
        ("search_genes_by_gene_model_chars", "organism_select_none"),
        ("search_genes_by_variant_characteristics", "organism_select_none"),
    ],
)
def test_wdk_param_013_the_organism_parameter_is_the_one_wdk_marks(
    fixture: str, marked: str
) -> None:
    """Exactly one parameter highlights reference organisms, whatever its name."""
    if needs_qa_recording(f"wdk/{fixture}.json"):
        pytest.skip(NEEDS_QA_RECORDING)
    search = WDKSearchResponse.model_validate(
        load_recorded(fixture).json_body()
    ).search_data

    assert [p.name for p in search.parameters or [] if p.is_organism] == [marked]


@pytest.mark.parametrize(
    "fixture",
    [
        "search_boolean_transcript",
        "search_genes_by_metabolic_pathway_hagai",
        "search_metrics_awstats",
        "search_with_a_hidden_required_parameter",
    ],
)
def test_wdk_param_013_a_search_without_the_mark_has_no_organism_parameter(
    fixture: str,
) -> None:
    """No parameter of a search whose declaration has no organism list is marked."""
    if needs_qa_recording(f"wdk/{fixture}.json"):
        pytest.skip(NEEDS_QA_RECORDING)
    search = WDKSearchResponse.model_validate(
        load_recorded(fixture).json_body()
    ).search_data

    assert [p.name for p in search.parameters or [] if p.is_organism] == []


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_mass_spec.json"), reason=NEEDS_QA_RECORDING
)
def test_wdk_param_013_an_organism_tree_of_samples_is_not_the_mark() -> None:
    """`ms_assay` carries `organismProperties` without `highlightReferenceOrganisms`."""
    search = WDKSearchResponse.model_validate(
        load_recorded("search_genes_by_mass_spec").json_body()
    ).search_data
    parameters = search.parameters or []

    assert (
        "organismProperties"
        in _parameter("search_genes_by_mass_spec", "ms_assay").properties
    )
    assert [p.name for p in parameters if p.is_organism] == []


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_location.json"), reason=NEEDS_QA_RECORDING
)
def test_wdk_param_013_an_organisms_property_is_not_the_mark() -> None:
    """Every GenesByLocation parameter lists `organisms`; only one is marked."""
    search = WDKSearchResponse.model_validate(
        load_recorded("search_genes_by_location").json_body()
    ).search_data
    parameters = search.parameters or []

    assert all("organisms" in p.properties for p in parameters)
    assert [p.name for p in parameters if p.is_organism] == ["organismSinglePick"]


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_ngs_snps.json"), reason=NEEDS_QA_RECORDING
)
def test_wdk_param_017_a_number_is_written_as_the_shortest_decimal() -> None:
    """An `isNumber` string takes `5` for `5.0` and never an exponent."""
    param = _parameter("search_genes_by_ngs_snps", "MinPercentMinorAlleles")

    assert param.read_stated(5.0) == StringValue(value="5")
    assert param.read_stated(1e-8) == StringValue(value="0.00000001")


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_metrics_awstats.json"), reason=NEEDS_QA_RECORDING
)
def test_wdk_param_017_a_date_is_an_iso_local_date() -> None:
    """A date-range bound in the basic ISO form is refused before WDK parses it."""
    param = _parameter("search_metrics_awstats", "date")

    with pytest.raises(StatedValuesError):
        param.read_stated({"min": "20250101"})


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_orthologs.json"), reason=NEEDS_QA_RECORDING
)
def test_wdk_param_017_a_boolean_is_no_vocabulary_term() -> None:
    """A `yes`/`no` vocabulary refuses `true` and names its terms."""
    param = _parameter("search_genes_by_orthologs", "isSyntenic")

    with pytest.raises(StatedValuesError, match="'yes', 'no'"):
        param.read_stated(True)


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_ngs_snps.json"), reason=NEEDS_QA_RECORDING
)
def test_wdk_param_019_an_empty_value_reads_only_where_it_is_allowed() -> None:
    """The upper bound that allows an empty value reads it; the lower bound refuses it."""
    upper = _parameter("search_genes_by_ngs_snps", "occurrences_upper")
    lower = _parameter("search_genes_by_ngs_snps", "occurrences_lower")

    assert upper.read_stated("") == StringValue(value="")
    with pytest.raises(StatedValuesError):
        lower.read_stated("")


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_variant_characteristics.json")
    or needs_qa_recording("wdk/search_genes_by_ngs_snps.json"),
    reason=NEEDS_QA_RECORDING,
)
def test_wdk_param_018_a_clause_states_type_and_is_range_from_its_facet() -> None:
    """The same statement shape binds a range clause and a member clause."""
    stats = FilterFacets.of(
        _parameter("search_genes_by_variant_characteristics", "gene_variant_stats")
    )
    samples = FilterFacets.of(
        _parameter("search_genes_by_ngs_snps", "variation_sample_meta")
    )

    ranged = stats.bind(
        FilterProposals.model_validate(
            [{"field": "total_variants", "value": {"min": 6}}]
        )
    )
    members = samples.bind(
        FilterProposals.model_validate([{"field": "sex", "value": ["female"]}])
    )

    assert ranged.filters == [
        NumberRange(
            field="total_variants",
            type="number",
            is_range=True,
            include_unknown=False,
            value=NumberBounds(min=6),
        )
    ]
    assert members.filters == [
        StringMembers(
            field="VAR_68bb04bd",
            type="string",
            is_range=False,
            include_unknown=False,
            value=["female"],
        )
    ]


@pytest.mark.skipif(
    needs_qa_recording("wdk/search_genes_by_variant_characteristics.json")
    or needs_qa_recording("wdk/search_genes_by_ngs_snps.json")
    or needs_qa_recording("wdk/ontology_term_summary_total_variants.json"),
    reason=NEEDS_QA_RECORDING,
)
def test_wdk_param_018_a_range_facets_bounds_come_only_from_its_term_summary() -> None:
    """The published `values` holds no range term; the term summary holds its range."""
    stats = _parameter("search_genes_by_variant_characteristics", "gene_variant_stats")
    samples = _parameter("search_genes_by_ngs_snps", "variation_sample_meta")
    facet = FilterFacets.of(stats).find("total_variants")
    summary = WDKOntologyTermSummary.model_validate(
        load_recorded("ontology_term_summary_total_variants").json_body()
    )

    for param in (stats, samples):
        ranged = {term.term for term in param.ontology if term.is_range}
        assert ranged
        assert ranged.isdisjoint(param.values or {})
    assert facet is not None
    assert facet.members == []
    assert FacetRange.of(summary, facet) == FacetRange(
        min=1, max=4823, records=5643, units="variants"
    )


def _refreshed_parameter(fixture: str, name: str) -> WDKParameter:
    listed = TypeAdapter(list[WDKParameter]).validate_python(
        load_recorded(fixture).json_body()
    )
    return next(p for p in listed if p.name == name)


_SPELLINGS = [
    (
        _parameter,
        "search_genes_by_gene_type",
        "geneType",
        MultiPickValue(values=["Protein Coding"]),
        '["protein coding"]',
    ),
    (
        _parameter,
        "search_genes_by_ngs_snps",
        "snp_class",
        SinglePickValue(value="missense"),
        "Missense",
    ),
    (
        _parameter,
        "search_genes_by_metabolic_pathway_hagai",
        "metabolic_pathway",
        SinglePickValue(value="glycolysis"),
        "Glycolysis",
    ),
    (
        _refreshed_parameter,
        "refresh_interpro_domain_pfam_on_dal972",
        "domain_typeahead",
        MultiPickValue(values=["pf00069"]),
        '["PF00069"]',
    ),
    (
        _parameter,
        "search_genes_by_taxon",
        "organism",
        MultiPickValue(values=["Plasmodium  falciparum 3D7"]),
        '["Plasmodium falciparum 3D7"]',
    ),
]


@pytest.mark.parametrize(("reader", "fixture", "name", "stated", "wire"), _SPELLINGS)
def test_wdk_param_020_a_term_is_sent_as_the_vocabulary_spells_it(
    reader: Callable[[str, str], WDKParameter],
    fixture: str,
    name: str,
    stated: ParamValue,
    wire: str,
) -> None:
    if needs_qa_recording(f"wdk/{fixture}.json"):
        pytest.skip(NEEDS_QA_RECORDING)
    param = reader(fixture, name)
    spec = ParamSpecNormalized(
        name=name, param_type=param.type, vocabulary=param.vocabulary
    )

    canonical = ParameterCanonicalizer({name: spec}).canonicalize({name: stated})

    assert to_wire(canonical[name]) == wire


def test_wdk_param_021_a_multi_pick_is_its_set_of_terms() -> None:
    held = MultiPickValue(values=["Plasmodium falciparum 3D7", "Plasmodium vivax P01"])

    assert same_value(
        held,
        MultiPickValue(values=["Plasmodium vivax P01", "Plasmodium falciparum 3D7"]),
    )
    assert not same_value(held, MultiPickValue(values=["Plasmodium vivax P01"]))
