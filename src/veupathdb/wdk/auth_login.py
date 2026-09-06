"""VEuPathDB credentials: password login, logout, and bearer validation."""

from __future__ import annotations

import base64
import binascii
import json
import time
from http import HTTPStatus

import httpx
import jwt
from jwt import PyJWK
from pydantic import BaseModel, ConfigDict, Field

from veupathdb.errors import ExternalServiceError
from veupathdb.logging import get_logger
from veupathdb.wdk.factory import get_site

logger = get_logger(__name__)

_JWT_MIN_SEGMENTS = 2

_IDENTITY_PROVIDER = "VEuPathDB identity provider"
_JWKS_PATH = "/jwks"
_JWKS_TIMEOUT_SECONDS = 15.0
_OAUTH_ALGORITHM = "ES512"
_SIGNING_KEY_CACHE_SECONDS = 120.0


def _is_guest_jwt(token: str) -> bool:
    parts = token.split(".")
    if len(parts) < _JWT_MIN_SEGMENTS:
        return True
    payload_b64 = parts[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded).decode("utf-8")
        payload = json.loads(raw)
    except ValueError, binascii.Error:
        return True
    return bool(payload.get("is_guest", False))


def extract_auth_cookie(set_cookie_headers: list[str]) -> str | None:
    """Return the first non-guest ``Authorization`` cookie value, or None."""
    candidates: list[str] = []
    for header in set_cookie_headers:
        if not header.startswith("Authorization="):
            continue
        value = header.split(";", 1)[0].split("=", 1)[1].strip('"')
        if value:
            candidates.append(value)
    for token in candidates:
        if not _is_guest_jwt(token):
            return token
    return None


async def password_login(
    site_id: str, email: str, password: str, *, redirect_url: str = "/"
) -> str | None:
    """Log in to a VEuPathDB site with email/password and return the non-guest
    WDK ``Authorization`` token (the value that feeds ``veupathdb_auth_token_ctx``),
    or None when the credentials are rejected."""

    site = get_site(site_id)
    payload = {"email": email, "password": password, "redirectUrl": redirect_url}
    async with httpx.AsyncClient(
        base_url=site.service_url, follow_redirects=False
    ) as client:
        response = await client.post("/login", json=payload)
        return extract_auth_cookie(response.headers.get_list("set-cookie"))


async def password_logout(site_id: str, auth_token: str) -> bool:
    """End the WDK session the token belongs to.

    WDK logs out whoever made the request and returns early for a guest, so the
    token travels as the request's own credential. The response is a redirect
    rather than JSON, which is why this does not go through the JSON client.
    """
    site = get_site(site_id)
    try:
        async with httpx.AsyncClient(
            base_url=site.service_url, follow_redirects=False
        ) as client:
            response = await client.get(
                "/logout", cookies={"Authorization": auth_token}
            )
    except httpx.HTTPError:
        return False
    return response.status_code < HTTPStatus.BAD_REQUEST


class VEuPathDBClaims(BaseModel):
    """The claims PathFinder reads from a VEuPathDB bearer token."""

    model_config = ConfigDict(extra="ignore")

    sub: str
    is_guest: bool = True


class _JWK(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kty: str
    crv: str = ""
    x: str = ""
    y: str = ""


class _JWKS(BaseModel):
    model_config = ConfigDict(extra="ignore")

    keys: list[_JWK] = Field(default_factory=list)

    def elliptic_curve_key(self) -> _JWK | None:
        """Return the signing key, which the OAuth server publishes as the EC one."""
        return next((key for key in self.keys if key.kty == "EC"), None)


_signing_keys: dict[str, tuple[float, PyJWK]] = {}


def _unavailable(jwks_url: str, reason: str) -> ExternalServiceError:
    """Report that no token can be verified right now."""
    logger.warning(
        "Cannot read the OAuth signing key", jwks_url=jwks_url, reason=reason
    )
    return ExternalServiceError(
        service=_IDENTITY_PROVIDER,
        detail=f"{_IDENTITY_PROVIDER} at {jwks_url} cannot be read: {reason}",
        status=HTTPStatus.SERVICE_UNAVAILABLE,
    )


async def _fetch_oauth_signing_key(oauth_url: str) -> PyJWK:
    """Read the elliptic-curve signing key from the OAuth server's JWKS."""
    jwks_url = f"{oauth_url.rstrip('/')}{_JWKS_PATH}"
    try:
        async with httpx.AsyncClient(timeout=_JWKS_TIMEOUT_SECONDS) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            jwks = _JWKS.model_validate(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        raise _unavailable(jwks_url, str(exc)) from exc

    key = jwks.elliptic_curve_key()
    if key is None:
        raise _unavailable(jwks_url, "the JWKS carries no elliptic-curve key")

    try:
        return PyJWK(
            {
                "kty": key.kty,
                "crv": key.crv,
                "x": key.x,
                "y": key.y,
                "alg": _OAUTH_ALGORITHM,
            },
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise _unavailable(jwks_url, f"the published key is unusable: {exc}") from exc


async def _get_oauth_signing_key(oauth_url: str) -> PyJWK:
    """Return the OAuth signing key, refetching it when the cached one expires."""
    cached = _signing_keys.get(oauth_url)
    if cached is not None and cached[0] > time.monotonic():
        return cached[1]

    key = await _fetch_oauth_signing_key(oauth_url)
    _signing_keys[oauth_url] = (time.monotonic() + _SIGNING_KEY_CACHE_SECONDS, key)
    return key


async def validate_oauth_token(token: str, oauth_url: str) -> VEuPathDBClaims | None:
    """Verify a VEuPathDB bearer token and return its claims, or None if invalid.

    The token is an ES512 JWT signed by the OAuth server. Issuer and audience
    are not checked: a site mints its tokens for its own client id, and every
    VEuPathDB site shares this signing key. Raises ExternalServiceError when the
    signing key cannot be read, which is not the token's fault.
    """
    key = await _get_oauth_signing_key(oauth_url)

    try:
        payload = jwt.decode(
            token,
            key=key,
            algorithms=[_OAUTH_ALGORITHM],
            options={"require": ["exp", "sub"], "verify_aud": False},
        )
        return VEuPathDBClaims.model_validate(payload)
    except jwt.PyJWTError, ValueError:
        logger.debug("Rejected a VEuPathDB bearer token")
        return None
