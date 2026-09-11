"""What a WDK 4xx becomes.

A validating endpoint answers a refusal with a validation bundle, served as
``text/plain`` like every other WDK error. Read as an opaque string it throws
away the only structured account of what the value got wrong.
"""

from __future__ import annotations

import pydantic

from veupathdb.domain.strategy.validation import StepValidation
from veupathdb.errors import WDKError, param_message_rows
from veupathdb.json_types import JSONArray

_BODY_EXCERPT = 200


def validation_bundle(body: str) -> StepValidation | None:
    """The bundle a refusal carries, or None when the body is prose."""
    try:
        return StepValidation.model_validate_json(body)
    except pydantic.ValidationError:
        return None


def bundle_rows(bundle: StepValidation) -> JSONArray:
    """One row per refused parameter, keyed by parameter name."""
    return param_message_rows(bundle.errors.by_key if bundle.errors else {})


def wdk_failure(method: str, path: str, status: int, body: str) -> WDKError:
    """Build the error a refusal becomes, keeping the per-parameter messages."""
    bundle = validation_bundle(body)
    if bundle is None:
        msg = f"{method} {path} -> HTTP {status}: {body[:_BODY_EXCERPT]}"
        return WDKError(msg, status=status)
    detail = "; ".join(bundle.messages()) or body[:_BODY_EXCERPT]
    keyed = bundle_rows(bundle)
    msg = f"{method} {path} -> HTTP {status} ({bundle.level}): {detail}"
    return WDKError(msg, status=status, errors=keyed or None)
