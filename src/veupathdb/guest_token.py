"""The one guest token this process sends where no researcher token applies.

A VEuPathDB site mints a guest for every request that carries no token, and one
guest token is valid on every site and on EDA, so the process mints it once.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx
import jwt
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from veupathdb.errors import WDKError
from veupathdb.settings import user_agent_header

GUEST_RENEWAL_MARGIN_SECONDS = 600
_MINT_TIMEOUT_SECONDS = 30.0
_AUTHORIZATION_PREFIX = "Authorization="


class GuestClaims(BaseModel):
    """The claims of a minted guest token that this client reads."""

    model_config = ConfigDict(extra="ignore")

    is_guest: bool
    exp: int


def authorization_cookies(set_cookie_headers: list[str]) -> list[str]:
    """Every non-empty ``Authorization`` value a response sets, in order."""
    values = (
        header.split(";", 1)[0].removeprefix(_AUTHORIZATION_PREFIX).strip('"')
        for header in set_cookie_headers
        if header.startswith(_AUTHORIZATION_PREFIX)
    )
    return [value for value in values if value]


@dataclass(frozen=True)
class _Held:
    value: SecretStr
    expires_at: int

    def fresh(self) -> bool:
        return time.time() < self.expires_at - GUEST_RENEWAL_MARGIN_SECONDS


@dataclass(frozen=True)
class Credential:
    """The token one request travels with, and whether it is the shared guest."""

    token: str = field(repr=False)
    guest: bool = False


class GuestTokens:
    """Mints the guest token once and hands it out until shortly before it expires."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._held: _Held | None = None
        self._lock = asyncio.Lock()

    async def token(self, service_url: str) -> str:
        """The guest token, minted at the WDK service root ``service_url`` if none is fresh."""
        held = self._held
        if held is not None and held.fresh():
            return held.value.get_secret_value()
        async with self._lock:
            if self._held is None or not self._held.fresh():
                self._held = await self._mint(service_url)
            return self._held.value.get_secret_value()

    async def renew(self, refused: str, service_url: str) -> str:
        """A guest token other than ``refused``, which a site answered with 401."""
        async with self._lock:
            if self._held is None or self._held.value.get_secret_value() == refused:
                self._held = await self._mint(service_url)
            return self._held.value.get_secret_value()

    async def _mint(self, service_url: str) -> _Held:
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(_MINT_TIMEOUT_SECONDS),
            headers=user_agent_header(),
        ) as client:
            try:
                response = await client.get(service_url)
            except httpx.HTTPError as error:
                msg = f"GET {service_url} for a guest token failed: {type(error).__name__}"
                raise WDKError(msg, status=502) from error
        minted = authorization_cookies(response.headers.get_list("set-cookie"))
        if not minted:
            msg = f"GET {service_url} set no guest Authorization cookie"
            raise WDKError(msg, status=502)
        claims = _claims(minted[0], service_url)
        if not claims.is_guest:
            msg = f"GET {service_url} set a token that is not a guest token"
            raise WDKError(msg, status=502)
        return _Held(value=SecretStr(minted[0]), expires_at=claims.exp)


def _claims(token: str, service_url: str) -> GuestClaims:
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return GuestClaims.model_validate(payload)
    except jwt.PyJWTError, ValidationError:
        msg = f"GET {service_url} set an Authorization cookie that is not a token"
        raise WDKError(msg, status=502) from None


class _InForce:
    def __init__(self) -> None:
        self.tokens = GuestTokens()


_in_force = _InForce()


def guest_tokens() -> GuestTokens:
    """The holder every WDK and EDA client of this process reads."""
    return _in_force.tokens


def use_guest_tokens(tokens: GuestTokens) -> None:
    """Replace the holder. For a test or a tool that owns the mint."""
    _in_force.tokens = tokens


__all__ = [
    "GUEST_RENEWAL_MARGIN_SECONDS",
    "Credential",
    "GuestClaims",
    "GuestTokens",
    "authorization_cookies",
    "guest_tokens",
    "use_guest_tokens",
]
