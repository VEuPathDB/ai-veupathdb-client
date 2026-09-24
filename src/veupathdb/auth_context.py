"""The VEuPathDB bearer the current request carries, and how a client resolves it."""

from contextvars import ContextVar

from veupathdb.errors import WDKLoginRequiredError
from veupathdb.settings import get_veupathdb_settings

veupathdb_auth_token_ctx: ContextVar[str | None] = ContextVar(
    "veupathdb_auth_token", default=None
)


def resolve_veupathdb_auth_token(auth_token: str | None = None) -> str | None:
    """The token a user-independent read travels with.

    The contextvar first, then the client's own token, then
    ``settings.veupathdb_auth_token``.
    """
    return (
        veupathdb_auth_token_ctx.get()
        or auth_token
        or get_veupathdb_settings().veupathdb_auth_token
    )


def resolve_user_auth_token(auth_token: str | None = None) -> str:
    """The token a call on a researcher's own data travels with.

    The contextvar first, then the client's own token. The deployment's token
    never stands in, so with neither the call is refused.
    """
    token = veupathdb_auth_token_ctx.get() or auth_token
    if not token:
        raise WDKLoginRequiredError
    return token


__all__ = [
    "resolve_veupathdb_auth_token",
    "veupathdb_auth_token_ctx",
]
