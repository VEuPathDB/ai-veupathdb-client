"""The VEuPathDB bearer the current request carries, and how a client resolves it."""

from contextvars import ContextVar

from veupathdb.settings import get_veupathdb_settings

veupathdb_auth_token_ctx: ContextVar[str | None] = ContextVar(
    "veupathdb_auth_token", default=None
)


def resolve_veupathdb_auth_token(auth_token: str | None = None) -> str | None:
    """The token a request travels with, in the order every service reads it.

    The contextvar first, then the client's own token, then
    ``settings.veupathdb_auth_token``.
    """
    return (
        veupathdb_auth_token_ctx.get()
        or auth_token
        or get_veupathdb_settings().veupathdb_auth_token
    )


__all__ = [
    "resolve_veupathdb_auth_token",
    "veupathdb_auth_token_ctx",
]
