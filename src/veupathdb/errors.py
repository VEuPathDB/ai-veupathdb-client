"""The refusals the VEuPathDB services and their parameter model raise."""

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Final

import pydantic
from pydantic import BaseModel, ConfigDict

from veupathdb.json_types import JSONArray


class VEuPathDBErrorCode(StrEnum):
    """The machine-readable cause a refusal names."""

    DATA_PARSING_ERROR = "DATA_PARSING_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SEARCH_NOT_FOUND = "SEARCH_NOT_FOUND"
    SITE_NOT_FOUND = "SITE_NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    WDK_ERROR = "WDK_ERROR"
    WDK_LOGIN_REQUIRED = "WDK_LOGIN_REQUIRED"


class VEuPathDBError[C: StrEnum](Exception):
    """Base refusal. Carries everything a problem+json response needs.

    The code enum is the type parameter, so a host application subclasses this
    base with its own ``StrEnum`` and keeps ``code`` typed as that enum. A
    handler that takes any refusal annotates ``VEuPathDBError[StrEnum]``.
    """

    def __init__(
        self,
        code: C,
        title: str,
        status: int = 400,
        detail: str | None = None,
        errors: JSONArray | None = None,
    ) -> None:
        self.code: Final[C] = code
        self.title = title
        self.status = status
        self.detail = detail
        self.errors = errors
        msg = f"{title}: {detail}" if detail else title
        super().__init__(msg)


class ValidationError(VEuPathDBError[VEuPathDBErrorCode]):
    """A value a search parameter does not accept."""

    def __init__(
        self,
        title: str = "Validation failed",
        detail: str | None = None,
        errors: JSONArray | None = None,
    ) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.VALIDATION_ERROR,
            title=title,
            status=422,
            detail=detail,
            errors=errors,
        )


class SiteNotFoundError(VEuPathDBError[VEuPathDBErrorCode]):
    """A site identifier this deployment does not serve."""

    def __init__(self, site_id: str, available: Sequence[str]) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.SITE_NOT_FOUND,
            title="Site not found",
            status=404,
            detail=f"Unknown site: {site_id}. Available: {list(available)}",
        )


class WDKError(VEuPathDBError[VEuPathDBErrorCode]):
    """Error from VEuPathDB WDK service.

    ``errors`` carries the per-parameter messages a refusal named, when it
    named any.
    """

    def __init__(
        self,
        detail: str,
        status: int = 502,
        errors: JSONArray | None = None,
    ) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.WDK_ERROR,
            title="VEuPathDB service error",
            status=status,
            detail=detail,
            errors=errors,
        )


class WDKLoginRequiredError(VEuPathDBError[VEuPathDBErrorCode]):
    """The request names no registered VEuPathDB user.

    VEuPathDB serves the WDK service to registered users only, so a guest or
    anonymous request cannot reach a search, a strategy or a gene set.
    """

    def __init__(self) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.WDK_LOGIN_REQUIRED,
            title="VEuPathDB login required",
            status=401,
            detail="Sign in to VEuPathDB to use searches, strategies and gene sets.",
        )


class ExternalServiceError(VEuPathDBError[VEuPathDBErrorCode]):
    """A non-WDK external service is unreachable or answers unexpectedly."""

    def __init__(self, service: str, detail: str, status: int = 502) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.EXTERNAL_SERVICE_ERROR,
            title=f"External service error: {service}",
            status=status,
            detail=detail,
        )


class DataParsingError(VEuPathDBError[VEuPathDBErrorCode]):
    """An external API returned data that does not match the expected shape."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.DATA_PARSING_ERROR,
            title="Data parsing failed",
            status=500,
            detail=detail,
        )


class ParamMessages(BaseModel):
    """One refused parameter and the messages that name the fault."""

    model_config = ConfigDict(frozen=True)

    param: str
    messages: list[str]


def param_message_rows(by_param: Mapping[str, Sequence[str]]) -> JSONArray:
    """The ``errors`` rows a per-parameter refusal carries."""
    return [
        ParamMessages(param=name, messages=list(texts)).model_dump(mode="json")
        for name, texts in by_param.items()
    ]


def validate_response[M: BaseModel](model: type[M], raw: object, context: str) -> M:
    """Validate an external API response and raise ``DataParsingError``."""
    try:
        return model.model_validate(raw)
    except pydantic.ValidationError as e:
        msg = f"Unexpected {context}: {e}"
        raise DataParsingError(msg) from e
