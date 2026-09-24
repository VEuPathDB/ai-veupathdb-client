"""The reference genomes an rnaseqrc upload may name, from the recorded site reads."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest
import respx
from tests.unit.wdk.vdi._wire import recorded

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.settings import VEuPathDBSettings, use_veupathdb_settings_source
from veupathdb.wdk.vdi.genomes import reference_genomes
from veupathdb.wdk.vdi.models import VdiDatasetDependency

_SERVICE = "https://plasmodb.org/plasmo/service"
_GENOMES = f"{_SERVICE}/record-types/organism/searches/GenomeDataTypes/reports/standard"


@pytest.fixture
def no_credential() -> Iterator[None]:
    """Both reads answer with no credential, so none is configured."""
    use_veupathdb_settings_source(lambda: VEuPathDBSettings(veupathdb_auth_token=None))
    reset = veupathdb_auth_token_ctx.set(None)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)
        use_veupathdb_settings_source(VEuPathDBSettings)


def _genome_rows() -> list[dict[str, str]]:
    raw = recorded("genome_data_types")
    assert isinstance(raw, dict)
    return [record["attributes"] for record in raw["records"]]


@pytest.mark.usefixtures("no_credential")
@respx.mock
async def test_reference_genomes_build_the_sites_identifier() -> None:
    respx.get(f"{_SERVICE}/").mock(
        return_value=httpx.Response(200, json=recorded("service_root"))
    )
    report = respx.post(_GENOMES).mock(
        return_value=httpx.Response(200, json=recorded("genome_data_types"))
    )

    genomes = await reference_genomes("plasmodb")

    rows = _genome_rows()
    assert len(genomes) == len(rows) == 64
    assert genomes == [
        VdiDatasetDependency(
            resource_identifier=f"PlasmoDB-71_{row['name_for_filenames']}_Genome",
            resource_display_name=row["organism_full"],
            resource_version="71",
        )
        for row in rows
    ]
    assert (
        VdiDatasetDependency(
            resource_identifier="PlasmoDB-71_Pfalciparum3D7_Genome",
            resource_display_name="Plasmodium falciparum 3D7",
            resource_version="71",
        )
        in genomes
    )
    sent = report.calls.last.request
    assert "authorization" not in sent.headers
    assert "cookie" not in sent.headers
    assert json.loads(sent.content) == {
        "searchConfig": {"parameters": {}},
        "reportConfig": {
            "attributes": ["organism_full", "name_for_filenames"],
            "pagination": {"offset": 0, "numRecords": -1},
        },
    }


_GIARDIA = "https://giardiadb.org/giardiadb/service"


@pytest.mark.usefixtures("no_credential")
@respx.mock
async def test_a_genome_whose_identifier_vdi_refuses_is_not_offered() -> None:
    respx.get(f"{_GIARDIA}/").mock(
        return_value=httpx.Response(200, json=recorded("giardiadb_service_root"))
    )
    respx.post(
        f"{_GIARDIA}/record-types/organism/searches/GenomeDataTypes/reports/standard"
    ).mock(
        return_value=httpx.Response(200, json=recorded("giardiadb_genome_data_types"))
    )

    genomes = await reference_genomes("giardiadb")

    raw = recorded("giardiadb_genome_data_types")
    assert isinstance(raw, dict)
    offered = {genome.resource_display_name for genome in genomes}
    listed = {record["attributes"]["organism_full"] for record in raw["records"]}
    assert len(raw["records"]) == 16
    assert len(genomes) == 13
    assert listed - offered == {
        "Giardia Assemblage A isolate WB Calgary",
        "Giardia Assemblage B isolate BAH15c1",
        "Giardia Assemblage B isolate GS Calgary",
    }
    assert max(len(genome.resource_identifier) for genome in genomes) == 50
