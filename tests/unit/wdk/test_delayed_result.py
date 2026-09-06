"""A delayed-result body arrives as a 2xx, so only its shape identifies it."""

from __future__ import annotations

import pytest

from veupathdb.wdk.delayed_result import (
    DELAYED_RESULT_MESSAGE,
    WDKDelayedResultError,
    is_delayed_result,
)

_SENTINEL = {"status": "accepted", "message": DELAYED_RESULT_MESSAGE}


class TestRecognisedByShape:
    def test_the_sentinel_body_is_a_delay(self) -> None:
        assert is_delayed_result(_SENTINEL)

    def test_the_message_alone_is_enough(self) -> None:
        # The status field is not the discriminator; the message is.
        assert is_delayed_result({"message": DELAYED_RESULT_MESSAGE})

    def test_a_real_answer_is_not_a_delay(self) -> None:
        assert not is_delayed_result({"meta": {"totalCount": 3}, "records": []})

    def test_an_empty_body_is_not_a_delay(self) -> None:
        assert not is_delayed_result(None)

    def test_a_list_body_is_not_a_delay(self) -> None:
        assert not is_delayed_result([{"message": DELAYED_RESULT_MESSAGE}])

    def test_an_unrelated_accepted_body_is_not_a_delay(self) -> None:
        assert not is_delayed_result({"status": "accepted"})


class TestItIsRetryable:
    def test_the_error_is_the_type_the_client_retries(self) -> None:
        # Retrying is the whole point: the result is being computed.
        error = WDKDelayedResultError()

        assert isinstance(error, Exception)
        assert str(error) == f"WDK returned {DELAYED_RESULT_MESSAGE}; result not ready"

    def test_it_can_be_raised_and_caught_by_type(self) -> None:
        with pytest.raises(WDKDelayedResultError):
            raise WDKDelayedResultError
