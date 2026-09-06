"""Typed refusals from the EDA service, one class per status class."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb.json_types import JSONArray, JSONObject

_COMPUTE_NOT_READY = "Compute results are not available"

_BAD_REQUEST = 400
_FORBIDDEN = 403
_CONFLICT = 409
_SERVER_ERROR = 500

_STUDY_ID_HINT = (
    "A dataset id where a study id belongs is refused as forbidden. "
    "Compute and visualization bodies take the STUDY_ id."
)

_OTHER_ACCOUNT_HINT = (
    "The analysis belongs to a different VEuPathDB account than the one "
    "signed in now. Open the study again to create one under this account."
)


class EdaError(VEuPathDBError):
    """Base for every EDA refusal."""

    def __init__(
        self,
        detail: str,
        status: int,
        errors: JSONArray | None = None,
    ) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.EXTERNAL_SERVICE_ERROR,
            title="Study service error",
            status=status,
            detail=detail,
            errors=errors,
        )


class EdaBadRequestError(EdaError):
    """A name or a type did not check out. The message is specific enough to repair."""


class EdaComputeNotReadyError(EdaError):
    """A compute-backed visualization whose job has not completed.

    The status is a conflict: the request is well formed and the analysis is
    not in a state that can answer it.
    """


class EdaInvalidInputError(EdaError):
    """The JSON did not deserialize. No variable was resolved."""


class EdaForbiddenError(EdaError):
    """Permission, or an id that is not a study id."""


class EdaNotFoundError(EdaError):
    """No such resource. A malformed job id lands here too."""


class EdaServerError(EdaError):
    """An unparseable date bound is an author error, not an outage."""


class _EdaKeyedErrors(BaseModel):
    """The 422 body's per-key messages, the only machine-readable rejection."""

    model_config = ConfigDict(extra="ignore")

    general: list[str] = Field(default_factory=list)
    by_key: dict[str, list[str]] = Field(
        default_factory=dict,
        validation_alias="byKey",
    )


class _EdaProblem(BaseModel):
    """The two refusal bodies the service returns."""

    model_config = ConfigDict(extra="ignore")

    status: str = ""
    message: str = ""
    errors: _EdaKeyedErrors | None = None


_BY_STATUS: dict[int, type[EdaError]] = {
    400: EdaBadRequestError,
    404: EdaNotFoundError,
    422: EdaInvalidInputError,
}


def eda_failure(method: str, path: str, status: int, body: str) -> EdaError:
    """Build the typed refusal for one non-2xx response."""
    problem = _parse(body)
    detail = f"{method} {path}: {problem.message or body[:500]}"
    keyed = _keyed(problem)
    if status == _BAD_REQUEST and _COMPUTE_NOT_READY in problem.message:
        return EdaComputeNotReadyError(detail, _CONFLICT, keyed)
    if status == _FORBIDDEN:
        return EdaForbiddenError(f"{detail}. {_forbidden_hint(path)}", status, keyed)
    if status >= _SERVER_ERROR:
        return EdaServerError(detail, status, keyed)
    if status in _BY_STATUS:
        return _BY_STATUS[status](detail, status, keyed)
    return EdaError(detail, status, keyed)


def _forbidden_hint(path: str) -> str:
    """A path under ``/users/`` names an account, so ownership is the refusal."""
    return _OTHER_ACCOUNT_HINT if path.startswith("/users/") else _STUDY_ID_HINT


def _parse(body: str) -> _EdaProblem:
    try:
        return _EdaProblem.model_validate_json(body)
    except ValueError:
        return _EdaProblem()


def _keyed(problem: _EdaProblem) -> JSONArray | None:
    if problem.errors is None:
        return None
    rows: JSONArray = [
        _row(key, messages) for key, messages in sorted(problem.errors.by_key.items())
    ]
    if problem.errors.general:
        rows.append(_row("general", problem.errors.general))
    return rows


def _row(key: str, messages: list[str]) -> JSONObject:
    widened: JSONArray = list(messages)
    return {"key": key, "messages": widened}
