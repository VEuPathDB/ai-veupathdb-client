"""Who the request's token names on a site, read from ``GET /users/current``."""

from __future__ import annotations

import httpx

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import VEuPathDBError
from veupathdb.logging import get_logger
from veupathdb.wdk.factory import get_site, get_wdk_client
from veupathdb.wdk.wdk_models import WDKUserInfo

logger = get_logger(__name__)


async def fetch_current_user(site_id: str) -> WDKUserInfo | None:
    """The WDK user the request's token names.

    None when the request carries no token, so a service account is never
    reported as the signed-in user, and None when WDK cannot answer.
    """
    if not veupathdb_auth_token_ctx.get():
        return None
    try:
        site = get_site(site_id)
        raw = await get_wdk_client(site.id).get("/users/current")
        return WDKUserInfo.model_validate(raw)
    except (httpx.HTTPError, VEuPathDBError, KeyError, ValueError) as exc:
        logger.debug("Cannot read the current WDK user", error=str(exc))
        return None


async def resolve_registered_email(token: str, site_id: str) -> str | None:
    """The email of the registered VEuPathDB user, or None for a guest."""
    reset_token = veupathdb_auth_token_ctx.set(token)
    try:
        user = await fetch_current_user(site_id)
    finally:
        veupathdb_auth_token_ctx.reset(reset_token)

    if user is None or user.is_guest:
        return None
    return user.email
