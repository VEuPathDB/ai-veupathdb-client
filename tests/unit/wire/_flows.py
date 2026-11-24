import json

from mitmproxy import http
from mitmproxy.test import tflow

from veupathdb.json_types import JSONObject
from veupathdb.testing.wire.signing import SigningKey

PLASMO = "qa.plasmodb.org"
SERVICE = "/plasmo.qa/service"


def flow(
    method: str,
    url: str,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> http.HTTPFlow:
    made = tflow.tflow()
    pairs = [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    made.request = http.Request.make(method, url, body, http.Headers(pairs))
    return made


def control(method: str, route: str, payload: object | None = None) -> http.HTTPFlow:
    body = json.dumps(payload).encode() if payload is not None else b""
    return flow(method, f"http://localhost:8080/__wire/{route}", body)


def registered(key: SigningKey, cassette: str | None) -> dict[str, str]:
    claims: JSONObject = {"sub": "e2e", "is_guest": False, "exp": 4102444800}
    if cassette is not None:
        claims["e2e_cassette"] = cassette
    return {"cookie": f"Authorization={key.sign(claims)}"}


def answer(made: http.HTTPFlow) -> http.Response:
    assert made.response is not None
    return made.response


def answered_json(made: http.HTTPFlow) -> object:
    return json.loads(answer(made).content or b"null")
