"""The reference genomes a site offers an upload, as the dependency objects VDI stores.

The identifier is the one the site's own upload form builds from the WDK build number
and the organism's file name.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from veupathdb.errors import validate_response
from veupathdb.json_types import JSONObject
from veupathdb.model import CamelModel
from veupathdb.wdk.factory import get_wdk_client
from veupathdb.wdk.vdi.models import DEPENDENCY_IDENTIFIER_MAX, VdiDatasetDependency
from veupathdb.wdk.wdk_models import WDKSearchConfig

_GENOME_SEARCH = "GenomeDataTypes"
_REPORT: JSONObject = {
    "attributes": ["organism_full", "name_for_filenames"],
    "pagination": {"offset": 0, "numRecords": -1},
}


class _ServiceRoot(CamelModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str
    build_number: str


class _GenomeRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    organism_full: str
    name_for_filenames: str


async def reference_genomes(site_id: str) -> list[VdiDatasetDependency]:
    """One dependency per genome the site lists, in the site's order.

    A genome whose identifier is longer than VDI accepts is left out: no upload can name it.
    """
    client = get_wdk_client(site_id)
    root = validate_response(_ServiceRoot, await client.get("/"), "WDK service root")
    answer = await client.run_search_report(
        "organism", _GENOME_SEARCH, WDKSearchConfig(), _REPORT
    )
    rows = [
        validate_response(_GenomeRow, record.attributes, "GenomeDataTypes row")
        for record in answer.records
    ]
    named = (
        (row, f"{root.project_id}-{root.build_number}_{row.name_for_filenames}_Genome")
        for row in rows
    )
    return [
        VdiDatasetDependency(
            resource_identifier=identifier,
            resource_display_name=row.organism_full,
            resource_version=root.build_number,
        )
        for row, identifier in named
        if len(identifier.encode()) <= DEPENDENCY_IDENTIFIER_MAX
    ]
