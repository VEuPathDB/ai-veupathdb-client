from __future__ import annotations

import json
from typing import cast

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm
from pydantic import BaseModel, ConfigDict

from veupathdb.json_types import JSONObject

ALGORITHM = "ES512"
CASSETTE_CLAIM = "e2e_cassette"
_KEY_ID = "wire"


class TokenClaims(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    is_guest: bool = True
    e2e_cassette: str | None = None


def _jwk(key: ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey) -> JSONObject:
    jwk = cast("JSONObject", json.loads(ECAlgorithm.to_jwk(key)))
    return {**jwk, "kid": _KEY_ID, "alg": ALGORITHM, "use": "sig"}


class SigningKey:
    def __init__(self, key: ec.EllipticCurvePrivateKey) -> None:
        self._key = key

    @classmethod
    def generate(cls) -> SigningKey:
        return cls(ec.generate_private_key(ec.SECP521R1()))

    def jwks(self) -> JSONObject:
        return {"keys": [_jwk(self._key.public_key())]}

    def private_jwk(self) -> JSONObject:
        return _jwk(self._key)

    def sign(self, claims: JSONObject) -> str:
        return jwt.encode(claims, self._key, algorithm=ALGORITHM)


def token_claims(token: str) -> TokenClaims | None:
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None
    return TokenClaims.model_validate(payload)
