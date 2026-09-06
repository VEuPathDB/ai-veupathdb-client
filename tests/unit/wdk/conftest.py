"""Fixtures for the WDK transport tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx

REGISTERED_TEST_TOKEN = "registered.transport.token"


@pytest.fixture
def wdk_request_token() -> Generator[str]:
    """Act as a registered VEuPathDB user.

    A test that addresses a resource inside a user's WDK account needs one:
    without it the transport refuses the call.
    """
    reset = veupathdb_auth_token_ctx.set(REGISTERED_TEST_TOKEN)
    yield REGISTERED_TEST_TOKEN
    veupathdb_auth_token_ctx.reset(reset)
