"""Who the request's token names on a site, read from ``GET /users/current``."""

from __future__ import annotations

import asyncio

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import WDKError
from veupathdb.wdk.factory import get_wdk_client
from veupathdb.wdk.wdk_models import WDKUserInfo

# An identity check is interactive: it answers fast or not at all, so it gets
# one attempt and this deadline instead of the site's retry policy.
IDENTITY_READ_TIMEOUT_SECONDS = 10.0

_TOKEN_REFUSED = frozenset({401, 403})


async def fetch_current_user(site_id: str) -> WDKUserInfo | None:
    """The WDK user the request's token names.

    None when the request carries no token, so a service account is never
    reported as the signed-in user, and None when the site refuses the token.
    A site that does not answer raises ``WDKError``.
    """
    if not veupathdb_auth_token_ctx.get():
        return None
    client = get_wdk_client(site_id)
    try:
        async with asyncio.timeout(IDENTITY_READ_TIMEOUT_SECONDS):
            raw = await client.get("/users/current", attempts=1)
    except TimeoutError as error:
        msg = f"GET /users/current did not answer in {IDENTITY_READ_TIMEOUT_SECONDS} s"
        raise WDKError(msg, status=502) from error
    except WDKError as error:
        if error.status in _TOKEN_REFUSED:
            return None
        raise
    return WDKUserInfo.model_validate(raw)


async def resolve_registered_email(token: str, site_id: str) -> str | None:
    """The email of the registered VEuPathDB user, or None for a guest.

    Raises ``WDKError`` when the site does not answer.
    """
    reset_token = veupathdb_auth_token_ctx.set(token)
    try:
        user = await fetch_current_user(site_id)
    finally:
        veupathdb_auth_token_ctx.reset(reset_token)

    if user is None or user.is_guest:
        return None
    return user.email
