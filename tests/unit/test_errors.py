"""The refusal base carries the code enum of whoever declares the subclass."""

from __future__ import annotations

from enum import StrEnum
from typing import assert_type

import pytest

from veupathdb.errors import (
    VEuPathDBError,
    VEuPathDBErrorCode,
    WDKError,
    WDKLoginRequiredError,
)


class HostErrorCode(StrEnum):
    """A code enum this client does not own."""

    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    WDK_ERROR = "WDK_ERROR"


class HostError(VEuPathDBError[HostErrorCode]):
    """What a host declares when it reuses the base for its own codes."""


def test_a_host_subclass_keeps_its_own_code_type() -> None:
    refusal = HostError(HostErrorCode.QUOTA_EXCEEDED, "Quota exceeded", status=429)

    assert_type(refusal.code, HostErrorCode)
    assert refusal.code is HostErrorCode.QUOTA_EXCEEDED
    assert refusal.status == 429
    assert str(refusal) == "Quota exceeded"


def test_a_host_refusal_is_caught_as_a_veupathdb_refusal() -> None:
    with pytest.raises(VEuPathDBError) as caught:
        raise HostError(HostErrorCode.WDK_ERROR, "WDK refused", detail="no such step")

    assert caught.value.code == "WDK_ERROR"
    assert str(caught.value) == "WDK refused: no such step"


def test_a_client_refusal_keeps_the_client_code_type() -> None:
    refusal = WDKLoginRequiredError()

    assert_type(refusal.code, VEuPathDBErrorCode)
    assert refusal.code is VEuPathDBErrorCode.WDK_LOGIN_REQUIRED
    assert refusal.status == 401


def test_one_handler_reads_both_hierarchies() -> None:
    """A host handler annotated with the bound takes the client's codes too."""

    def status_of(refusal: VEuPathDBError[StrEnum]) -> int:
        return refusal.status

    assert status_of(HostError(HostErrorCode.QUOTA_EXCEEDED, "Quota", 429)) == 429
    assert status_of(WDKError("upstream said no")) == 502


# Nouns a consuming application owns and this package does not model. A refusal
# served to that application's users may not name one.
CONSUMER_NOUNS = ("gene set", "conversation", "experiment", "workbench")


def test_the_login_refusal_states_the_condition_and_names_no_consumer_entity() -> None:
    refusal = WDKLoginRequiredError()
    detail = refusal.detail or ""
    prose = f"{refusal.title} {detail} {WDKLoginRequiredError.__doc__}".lower()

    assert "registered" in detail.lower()
    assert [noun for noun in CONSUMER_NOUNS if noun in prose] == []
