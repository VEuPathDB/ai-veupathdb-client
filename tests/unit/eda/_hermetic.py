"""The recorded EDA wire the hermetic client tests share."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda.client import EdaClient
from veupathdb.eda.models import (
    EdaComparator,
    EdaDifferentialExpressionConfig,
    EdaLabeledRange,
    EdaStringSetFilter,
    EdaVariableSpec,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR


@pytest.fixture(autouse=True)
def registered_token() -> Iterator[None]:
    """Every hermetic call travels as a registered user."""
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


def fixture(name: str) -> object:
    return json.loads((FIXTURE_DIR / name).read_text())


def eda_client(handler: httpx.MockTransport) -> EdaClient:
    return EdaClient(base_url="https://plasmodb.org/eda", transport=handler)


def species_filter() -> EdaStringSetFilter:
    return EdaStringSetFilter(
        entity_id="GENE_PHENOTYPE_DATA_ENTITY",
        variable_id="VAR_035294d0",
        string_set=["P. berghei"],
    )


def de_config() -> EdaDifferentialExpressionConfig:
    return EdaDifferentialExpressionConfig(
        identifier_variable=EdaVariableSpec(
            entity_id="ENT_fd574cd6", variable_id="VEUPATHDB_GENE_ID"
        ),
        value_variable=EdaVariableSpec(
            entity_id="ENT_fd574cd6", variable_id="SEQUENCE_READ_COUNT_SENSE"
        ),
        comparator=EdaComparator(
            variable=EdaVariableSpec(
                entity_id="ENT_8151325d", variable_id="VAR_081ab087"
            ),
            group_a=[EdaLabeledRange(label="normal")],
            group_b=[EdaLabeledRange(label="febrile")],
        ),
    )
