"""A guest token a hermetic suite mints with no network."""

from __future__ import annotations

import httpx
import jwt

from veupathdb.guest_token import GuestTokens

_HERMETIC_SIGNING_KEY = "hermetic-guest-signing-key-with-32-bytes"

HERMETIC_GUEST_TOKEN = jwt.encode(
    {"is_guest": True, "exp": 4102444800, "sub": "hermetic-guest"},
    _HERMETIC_SIGNING_KEY,
    algorithm="HS256",
)


def _mint(request: httpx.Request) -> httpx.Response:
    del request
    return httpx.Response(
        200,
        json={},
        headers={"set-cookie": f"Authorization={HERMETIC_GUEST_TOKEN};Path=/"},
    )


def hermetic_guest_tokens() -> GuestTokens:
    """A holder whose mint answers ``HERMETIC_GUEST_TOKEN`` without a network."""
    return GuestTokens(transport=httpx.MockTransport(_mint))
