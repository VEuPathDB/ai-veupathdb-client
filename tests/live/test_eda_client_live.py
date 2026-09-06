"""Live EDA: the recorded fixtures still describe the deployment.

Gated on WDK_TEST_TOKEN, or WDK_TEST_EMAIL/WDK_TEST_PASSWORD (skipped unset).
"""

from __future__ import annotations

import json

import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda.factory import get_eda_client
from veupathdb.eda.models import (
    EdaStringSetFilter,
    EdaStudiesResponse,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]


_PHENOTYPE_STUDY = "STUDY_53f554ec6a"
_PHENOTYPE_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"


async def test_the_live_study_catalog_still_parses(require_wdk_creds: str) -> None:
    token = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        studies = await get_eda_client("plasmodb").list_studies()
    finally:
        veupathdb_auth_token_ctx.reset(token)
    assert len(studies) > 500
    assert any(s.source_type == "user_submitted" for s in studies)


async def test_the_recorded_fields_are_still_a_subset_of_the_live_ones(
    require_wdk_creds: str,
) -> None:
    """A field the fixture carries and the wire dropped is drift worth failing on."""
    recorded = EdaStudiesResponse.model_validate(
        json.loads((FIXTURE_DIR / "studies_list.json").read_text())
    )
    token = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        live = await get_eda_client("plasmodb").list_studies()
    finally:
        veupathdb_auth_token_ctx.reset(token)
    # A user study is visible per project and per account, so only the
    # curated catalog is a stable subset across hosts and days.
    live_ids = {s.id for s in live if s.source_type == "curated"}
    recorded_ids = {s.id for s in recorded.studies if s.source_type == "curated"}
    assert recorded_ids <= live_ids


async def test_a_live_filtered_count_matches_the_recorded_one(
    require_wdk_creds: str,
) -> None:
    token = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        client = get_eda_client("plasmodb")
        unfiltered = await client.count(
            study_id=_PHENOTYPE_STUDY, entity_id=_PHENOTYPE_ENTITY, filters=[]
        )
        filtered = await client.count(
            study_id=_PHENOTYPE_STUDY,
            entity_id=_PHENOTYPE_ENTITY,
            filters=[
                EdaStringSetFilter(
                    entity_id=_PHENOTYPE_ENTITY,
                    variable_id="VAR_035294d0",
                    string_set=["P. berghei"],
                )
            ],
        )
    finally:
        veupathdb_auth_token_ctx.reset(token)
    assert unfiltered == 4279
    assert filtered == 4011


async def test_an_out_of_vocabulary_value_returns_zero_not_an_error(
    require_wdk_creds: str,
) -> None:
    """The 200-with-count-0 class the authoring validator is the only guard for."""
    token = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        count = await get_eda_client("plasmodb").count(
            study_id=_PHENOTYPE_STUDY,
            entity_id=_PHENOTYPE_ENTITY,
            filters=[
                EdaStringSetFilter(
                    entity_id=_PHENOTYPE_ENTITY,
                    variable_id="VAR_a8ad31c0",
                    string_set=["maybe"],
                )
            ],
        )
    finally:
        veupathdb_auth_token_ctx.reset(token)
    assert count == 0
