"""The VEuPathDB bearer the current request carries, and how a client resolves it."""

from contextvars import ContextVar

from veupathdb.errors import WDKLoginRequiredError

veupathdb_auth_token_ctx: ContextVar[str | None] = ContextVar(
    "veupathdb_auth_token", default=None
)


def resolve_user_auth_token(auth_token: str | None = None) -> str:
    """The token a call on a researcher's own data travels with.

    The contextvar first, then the client's own token. The guest token never
    stands in, so with neither the call is refused.
    """
    token = veupathdb_auth_token_ctx.get() or auth_token
    if not token:
        raise WDKLoginRequiredError
    return token


__all__ = [
    "veupathdb_auth_token_ctx",
]
