"""The recorded VDI bodies the hermetic client tests read."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk.vdi.client import VdiClient

FIXTURES = Path(__file__).resolve().parent / "fixtures"

BASE_URL = "https://plasmodb.org/vdi"
TOKEN = "registered.vdi.token"
PROBE_ID = "soV5JEQEcF00p"


@pytest.fixture
def registered_token() -> Iterator[str]:
    reset = veupathdb_auth_token_ctx.set(TOKEN)
    try:
        yield TOKEN
    finally:
        veupathdb_auth_token_ctx.reset(reset)


def recorded(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def vdi_client(handler: httpx.MockTransport) -> VdiClient:
    return VdiClient(base_url=BASE_URL, transport=handler)
