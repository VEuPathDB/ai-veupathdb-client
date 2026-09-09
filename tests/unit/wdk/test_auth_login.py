"""VEuPathDB bearer tokens are ES512 JWTs verified against the OAuth JWKS."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import httpx
import jwt
import pytest
import respx
import structlog.testing
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from veupathdb.errors import ExternalServiceError
from veupathdb.wdk.auth_login import (
    password_logout,
    validate_oauth_token,
)

OAUTH_URL = "https://oauth.test"
JWKS_URL = f"{OAUTH_URL}/jwks"


def _b64(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unverified(token: str) -> dict[str, Any]:
    claims: dict[str, Any] = jwt.decode(token, options={"verify_signature": False})
    return claims


def _key_pair() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP521R1())


def _jwks(private_key: ec.EllipticCurvePrivateKey) -> dict[str, Any]:
    """Build a JWKS shaped like the VEuPathDB OAuth server's."""
    public = ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return {
        "keys": [
            {
                "kid": "0",
                "use": "sig",
                "fmt": "RAW",
                "kty": "oct",
                "alg": "HS512",
                "k": "<your_client_secret>",
            },
            {
                "kid": "1",
                "use": "sig",
                "fmt": "X.509",
                "kty": "EC",
                "alg": "ES512",
                "crv": public["crv"],
                "x": public["x"],
                "y": public["y"],
            },
        ],
    }


def _token(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    is_guest: bool = False,
    expires_in: int = 3600,
) -> str:
    return jwt.encode(
        {
            "sub": "1248677203",
            "is_guest": is_guest,
            "iss": "https://auth.veupathdb.org",
            "aud": "apiComponentSite",
            "azp": "apiComponentSite",
            "exp": int(time.time()) + expires_in,
        },
        private_key,
        algorithm="ES512",
    )


@respx.mock
async def test_a_registered_user_token_validates() -> None:
    private_key = _key_pair()
    respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=_jwks(private_key)))

    claims = await validate_oauth_token(_token(private_key), OAUTH_URL)

    assert claims is not None
    assert claims.sub == "1248677203"
    assert claims.is_guest is False


@respx.mock
async def test_a_guest_token_validates_and_reports_the_guest_flag() -> None:
    private_key = _key_pair()
    respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=_jwks(private_key)))

    claims = await validate_oauth_token(_token(private_key, is_guest=True), OAUTH_URL)

    assert claims is not None
    assert claims.is_guest is True


@respx.mock
async def test_an_expired_token_is_rejected() -> None:
    private_key = _key_pair()
    respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=_jwks(private_key)))
    expired = _token(private_key, expires_in=-60)

    assert _unverified(expired)["exp"] < int(time.time())
    assert await validate_oauth_token(expired, OAUTH_URL) is None


@respx.mock
async def test_a_token_signed_by_another_key_is_rejected() -> None:
    served, signer = _key_pair(), _key_pair()
    respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=_jwks(served)))

    assert _jwks(served)["keys"][1]["x"] != _jwks(signer)["keys"][1]["x"]
    assert await validate_oauth_token(_token(signer), OAUTH_URL) is None


@respx.mock
async def test_a_token_signed_with_the_public_key_as_an_hmac_secret_is_rejected() -> (
    None
):
    """The canonical algorithm-confusion attack: HS256 keyed by the public key."""
    private_key = _key_pair()
    respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=_jwks(private_key)))
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    # PyJWT refuses to sign with an asymmetric key, which is the attack it
    # prevents; the forged token is assembled by hand to reach the verifier.
    header = _b64({"alg": "HS256", "typ": "JWT"})
    payload = _b64({"sub": "1", "is_guest": False, "exp": int(time.time()) + 3600})
    signing_input = f"{header}.{payload}".encode()
    signature = base64.urlsafe_b64encode(
        hmac.new(public_bytes, signing_input, hashlib.sha256).digest(),
    ).rstrip(b"=")
    forged = f"{header}.{payload}.{signature.decode()}"

    assert jwt.get_unverified_header(forged)["alg"] == "HS256"
    assert await validate_oauth_token(forged, OAUTH_URL) is None


@respx.mock
async def test_a_token_without_the_required_claims_is_rejected() -> None:
    private_key = _key_pair()
    respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=_jwks(private_key)))
    no_subject = jwt.encode(
        {"is_guest": False, "exp": int(time.time()) + 3600},
        private_key,
        algorithm="ES512",
    )

    assert "sub" not in _unverified(no_subject)
    assert await validate_oauth_token(no_subject, OAUTH_URL) is None


@respx.mock
async def test_a_jwks_without_an_elliptic_curve_key_cannot_validate() -> None:
    respx.get(JWKS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"keys": [{"kid": "0", "kty": "oct", "alg": "HS512", "k": "abc"}]},
        ),
    )

    with pytest.raises(ExternalServiceError) as caught:
        await validate_oauth_token(_token(_key_pair()), OAUTH_URL)
    assert caught.value.status == 503


@respx.mock
async def test_a_jwks_whose_coordinates_are_malformed_cannot_validate() -> None:
    private_key = _key_pair()
    corrupt = _jwks(private_key)
    corrupt["keys"][1]["x"] = "!!!not-base64!!!"
    respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=corrupt))

    with pytest.raises(ExternalServiceError) as caught:
        await validate_oauth_token(_token(private_key), OAUTH_URL)
    assert caught.value.status == 503
    assert "identity provider" in caught.value.title


@respx.mock
async def test_an_oauth_server_answering_an_error_cannot_validate() -> None:
    respx.get(JWKS_URL).mock(return_value=httpx.Response(503, text="down"))

    with pytest.raises(ExternalServiceError) as caught:
        await validate_oauth_token(_token(_key_pair()), OAUTH_URL)
    assert caught.value.status == 503
    assert "identity provider" in caught.value.title


@respx.mock
async def test_an_unreachable_oauth_server_cannot_validate() -> None:
    respx.get(JWKS_URL).mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(ExternalServiceError) as caught:
        await validate_oauth_token(_token(_key_pair()), OAUTH_URL)
    assert caught.value.status == 503


@respx.mock
async def test_the_signing_key_is_fetched_once_for_many_tokens() -> None:
    private_key = _key_pair()
    route = respx.get(JWKS_URL).mock(
        return_value=httpx.Response(200, json=_jwks(private_key)),
    )

    assert await validate_oauth_token(_token(private_key), OAUTH_URL) is not None
    assert await validate_oauth_token(_token(private_key), OAUTH_URL) is not None

    assert route.call_count == 1


@respx.mock
async def test_the_logout_sends_the_token_as_the_authorization_cookie() -> None:
    route = respx.get("https://plasmodb.org/plasmo/service/logout").mock(
        return_value=httpx.Response(302, headers={"location": "/"})
    )

    assert await password_logout("plasmodb", "a-token") is True
    assert route.calls.last.request.headers["cookie"] == "Authorization=a-token"


@respx.mock
async def test_a_refused_logout_reports_that_no_session_ended() -> None:
    respx.get("https://plasmodb.org/plasmo/service/logout").mock(
        return_value=httpx.Response(500, text="boom")
    )

    with structlog.testing.capture_logs() as entries:
        assert await password_logout("plasmodb", "a-token") is False

    assert [entry["event"] for entry in entries if entry["log_level"] == "warning"] == [
        "VEuPathDB did not end the session"
    ]


@respx.mock
async def test_an_unreachable_site_reports_that_no_session_ended() -> None:
    respx.get("https://plasmodb.org/plasmo/service/logout").mock(
        side_effect=httpx.ConnectError("refused")
    )

    with structlog.testing.capture_logs() as entries:
        assert await password_logout("plasmodb", "a-token") is False

    assert [entry["event"] for entry in entries if entry["log_level"] == "warning"] == [
        "VEuPathDB did not end the session"
    ]
