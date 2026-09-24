"""The recorded gene-id distributions read back as the counts the site answered."""

from __future__ import annotations

import pytest

from veupathdb.testing.eda_fixtures import recorded_distribution


@pytest.mark.parametrize(
    ("name", "subset_size", "distinct_genes"),
    [
        ("gene_id_distribution_phenotype_filtered", 4011, 5595),
        ("gene_id_distribution_phenotype_unfiltered", 4279, 5803),
        ("gene_id_distribution_de_filtered", 5114, 842),
        ("gene_id_distribution_de_unfiltered", 68640, 5720),
    ],
)
def test_a_distribution_counts_distinct_gene_ids_and_not_rows(
    name: str, subset_size: int, distinct_genes: int
) -> None:
    statistics = recorded_distribution(name).statistics

    assert statistics.subset_size == subset_size
    assert statistics.num_distinct_values == distinct_genes


def test_a_bin_is_one_gene_id_and_its_row_count() -> None:
    first = recorded_distribution("gene_id_distribution_de_unfiltered").histogram[0]

    assert first.bin_label == "PF3D7_0100100"
    assert first.value == 12


def test_a_name_the_store_does_not_hold_is_refused() -> None:
    with pytest.raises(FileNotFoundError):
        recorded_distribution("gene_id_distribution_nowhere")
