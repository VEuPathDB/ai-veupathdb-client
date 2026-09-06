"""The VEuPathDB bearer the current request carries."""

from contextvars import ContextVar

veupathdb_auth_token_ctx: ContextVar[str | None] = ContextVar(
    "veupathdb_auth_token", default=None
)
