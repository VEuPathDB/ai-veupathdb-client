"""WDK-HTTP-002 and WDK-VALID-006 over the recorded refusals."""

from __future__ import annotations

from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk._failures import bundle_rows, validation_bundle, wdk_failure

_REFRESH = (
    "/record-types/transcript/searches/GenesByLocation/refreshed-dependent-params"
)


def test_wdk_http_002_a_422_serves_json_under_text_plain() -> None:
    """The recorded 422 is `text/plain` and its body parses as a bundle."""
    recorded = load_recorded("refresh_with_a_value_outside_the_vocabulary")

    assert recorded.provenance.status == 422
    assert recorded.provenance.content_type == "text/plain"
    assert validation_bundle(recorded.raw_text()) is not None


def test_wdk_http_002_the_status_is_what_the_refusal_carries() -> None:
    """A refusal keeps the status it arrived with, whatever the body is."""
    recorded = load_recorded("refresh_without_changed_param")
    refusal = wdk_failure(
        "POST", _REFRESH, recorded.provenance.status, recorded.raw_text()
    )

    assert refusal.status == 400
    assert validation_bundle(recorded.raw_text()) is None


def test_wdk_valid_006_an_unspecified_level_carries_prose_and_no_keyed_row() -> None:
    """`UNSPECIFIED` marks a bundle whose message names no parameter."""
    recorded = load_recorded("refresh_with_a_value_outside_the_vocabulary")
    bundle = validation_bundle(recorded.raw_text())

    assert bundle is not None
    assert bundle.level == "UNSPECIFIED"
    assert bundle_rows(bundle) == []
    assert "is invalid" in "; ".join(bundle.messages())


def test_wdk_valid_006_a_keyed_bundle_names_the_parameter() -> None:
    """A bundle with `byKey` entries becomes one row per refused parameter."""
    body = (
        '{"level": "SEMANTIC", "isValid": false, '
        '"errors": {"general": [], "byKey": {"organism": ["is not a term"]}}}'
    )
    bundle = validation_bundle(body)

    assert bundle is not None
    assert bundle_rows(bundle) == [{"param": "organism", "messages": ["is not a term"]}]
