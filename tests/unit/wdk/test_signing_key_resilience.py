"""One dropped connection to the OAuth server must not fail a request."""

import time
from typing import Any

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from veupathdb.errors import ExternalServiceError
from veupathdb.wdk import auth_login
from veupathdb.wdk.auth_login import validate_oauth_token

OAUTH_URL = "https://oauth.test"
JWKS_URL = f"{OAUTH_URL}/jwks"


def _key_pair() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP521R1())


def _jwks(private_key: ec.EllipticCurvePrivateKey) -> dict[str, Any]:
    public = ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return {
        "keys": [
            {
                "kid": "1",
                "use": "sig",
                "kty": "EC",
                "alg": "ES512",
                "crv": public["crv"],
                "x": public["x"],
                "y": public["y"],
            },
        ],
    }


def _token(private_key: ec.EllipticCurvePrivateKey) -> str:
    return jwt.encode(
        {
            "sub": "1248677203",
            "is_guest": False,
            "iss": "https://auth.veupathdb.org",
            "aud": "apiComponentSite",
            "azp": "apiComponentSite",
            "exp": int(time.time()) + 3600,
        },
        private_key,
        algorithm="ES512",
    )


@pytest.fixture(autouse=True)
def _no_cached_key() -> None:
    auth_login.forget_signing_keys()


@respx.mock
async def test_a_dropped_connection_is_retried() -> None:
    private_key = _key_pair()
    route = respx.get(JWKS_URL).mock(
        side_effect=[
            httpx.ConnectError(""),
            httpx.Response(200, json=_jwks(private_key)),
        ],
    )

    assert await validate_oauth_token(_token(private_key), OAUTH_URL) is not None
    assert route.call_count == 2


@respx.mock
async def test_the_last_good_key_answers_while_the_server_is_unreachable() -> None:
    private_key = _key_pair()
    respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=_jwks(private_key)))
    assert await validate_oauth_token(_token(private_key), OAUTH_URL) is not None

    auth_login.expire_signing_keys()
    respx.get(JWKS_URL).mock(side_effect=httpx.ReadTimeout(""))

    assert await validate_oauth_token(_token(private_key), OAUTH_URL) is not None


@respx.mock
async def test_a_failure_with_no_key_ever_read_names_its_cause() -> None:
    respx.get(JWKS_URL).mock(side_effect=httpx.ReadTimeout(""))

    with pytest.raises(ExternalServiceError) as caught:
        await validate_oauth_token(_token(_key_pair()), OAUTH_URL)

    assert caught.value.status == 503
    assert "ReadTimeout" in (caught.value.detail or "")
